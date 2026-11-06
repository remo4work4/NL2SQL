"""RAG 检索器：双路召回（向量 + BM25）→ RRF 融合 → 交叉编码器重排序。

召回链路（按序）：
  1. 向量路：BGE 稠密向量 → Chroma cosine Top-K（低于阈值丢弃）
  2. BM25 路：jieba 分词 → rank_bm25 词法打分 Top-K
  3. 关键词路：表/字段业务名精确命中（作为第三路，高置信信号）
  4. RRF 融合：score = Σ 1/(60 + rank)，三路合并排序
  5. 重排序：bge-reranker-v2-m3 交叉编码器对融合 Top-N 打分重排，
     低于阈值候选丢弃；全部不达标时回退 RRF 排序
  6. JOIN 闭包：命中表的一跳关联表一并注入
  7. 上限裁剪：最多 rag_max_tables 张

全部未命中时返回空列表，由调用方兜底全量注入（与改造前行为一致）。
任一路不可用（模型缺失/索引为空/异常）自动降级跳过，不阻断主流程。

BM25 索引按 app.db mtime 惰性构建缓存；稠密/重排模型懒加载单例。
"""
import logging
import threading

import chromadb
import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.core import semantic_meta
from app.core.config import settings

logger = logging.getLogger("nl2sql.rag")
jieba.setLogLevel(logging.WARNING)

# Phase 8 多进程：限制每 worker 的 torch 线程数，避免 2 个 worker 推理时
# CPU 超额订阅（8 核机器 2×全核 = 打满，父进程心跳轮询超时会被 uvicorn
# 误判为 hung 而杀进程；实测发生过）。每 worker 4 线程 × 2 worker = 8。
import os

import torch

_torch_threads = max(1, min(settings.torch_threads, os.cpu_count() or 1))
torch.set_num_threads(_torch_threads)
logger.info("torch 推理线程数（本 worker）: %d", _torch_threads)

COLLECTION_NAME = "schema_meta"
RRF_K = 60

# ---- 懒加载单例（稠密 embedding / 交叉编码器 / Chroma 客户端）----
_embedder: SentenceTransformer | None = None
_embedder_lock = threading.Lock()
_reranker: CrossEncoder | None = None
_reranker_lock = threading.Lock()
_client: chromadb.PersistentClient | None = None
_bm25_cache: dict = {"ts": 0.0, "bm25": None, "table_names": []}


def _pid_alive(pid: int) -> bool:
    """进程存活探测（Windows/Linux 均支持 signal 0 探测）。"""
    import os
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _model_load_lock(name: str):
    """跨进程模型加载互斥锁（Redis SET NX，Phase 8）。

    多 worker 同时冷启动时串行化加载：避免两份 fp32 权重的瞬时内存尖峰叠加。
    锁值记录持有者 PID：被 kill/OOM 的进程没机会执行 finally 释放，会出现
    僵尸锁（实测阻塞后续加载直到 TTL 过期）——探测到持锁进程已死即回收。
    Redis 不可用时退化为无锁加载（原行为）。
    """
    import os
    import time
    from contextlib import contextmanager

    @contextmanager
    def _locked():
        key = f"nl2sql:modelload:{name}"
        if not settings.redis_url:
            yield
            return
        r = None
        token = str(os.getpid())
        acquired = False
        try:
            import redis

            r = redis.Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
            deadline = time.monotonic() + 300
            while not acquired and time.monotonic() < deadline:
                acquired = bool(r.set(key, token, nx=True, ex=120))
                if not acquired:
                    holder = r.get(key)
                    holder_pid = None
                    if holder:
                        try:
                            holder_pid = int(holder.decode())
                        except ValueError:
                            holder_pid = None
                    if holder_pid and holder_pid != os.getpid() and not _pid_alive(holder_pid):
                        logger.warning("回收僵尸模型加载锁（holder pid %s 已死）", holder_pid)
                        r.delete(key)
                        continue
                    logger.info("模型加载等待（%s 被 pid %s 持锁）", name, holder_pid)
                    time.sleep(2)
            yield
        except Exception as e:
            logger.warning("模型加载锁不可用（%s），无锁加载", e)
            yield
        finally:
            if r is not None and acquired:
                try:
                    r.delete(key)
                except Exception:
                    pass

    return _locked()


def get_embedder() -> SentenceTransformer:
    """懒加载 BGE 稠密模型（本地目录优先，缺失时在线下载；跨进程串行加载）。"""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                model_dir = settings.bge_model_dir_file
                if (model_dir / "config.json").exists():
                    path = str(model_dir)
                    logger.info("加载本地 BGE 模型: %s", path)
                else:
                    import os
                    os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
                    path = settings.bge_model
                    logger.info("本地 BGE 目录缺失，在线下载: %s", settings.bge_model)
                with _model_load_lock("embedder"):
                    _embedder = SentenceTransformer(path)
    return _embedder


def get_reranker() -> CrossEncoder:
    """懒加载交叉编码器（重排序；跨进程串行加载）。"""
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                model_dir = settings.reranker_model_dir_file
                if (model_dir / "config.json").exists():
                    path = str(model_dir)
                    logger.info("加载本地重排模型: %s", path)
                else:
                    import os
                    os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
                    path = settings.reranker_model
                    logger.info("本地重排模型缺失，在线下载: %s", settings.reranker_model)
                with _model_load_lock("reranker"):
                    _reranker = CrossEncoder(path)
    return _reranker


def get_collection():
    """Chroma 集合（进程内单例）。

    Phase 9：chroma_mode=server 时走 Chroma 独立服务（多实例共享索引），
    否则进程内 PersistentClient（单机模式）。
    """
    global _client
    if _client is None:
        if settings.chroma_mode == "server":
            _client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        else:
            settings.chroma_dir_file.parent.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(settings.chroma_dir_file))
    return _client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def embed_texts(texts: list[str]) -> np.ndarray:
    """BGE 批量向量化（L2 归一化，配合 cosine 距离）。

    Phase 9：model_service_url 配置时走独立模型服务（多实例共享一份模型），
    否则进程内加载。
    """
    if settings.model_service_url:
        return np.asarray(_remote_embed(texts))
    model = get_embedder()
    return np.asarray(model.encode(texts, normalize_embeddings=True))


_http: "object | None" = None


def _get_http():
    """同步 httpx 客户端（模型服务调用，进程内单例）。"""
    global _http
    if _http is None:
        import httpx
        _http = httpx.Client(base_url=settings.model_service_url, timeout=60, trust_env=False)
    return _http


def _remote_embed(texts: list[str]) -> list[list[float]]:
    resp = _get_http().post("/embed", json={"texts": texts})
    resp.raise_for_status()
    return resp.json()["vectors"]


def _remote_rerank(question: str, pairs: list[tuple[str, str]]) -> list[tuple[str, float]]:
    resp = _get_http().post("/rerank", json={"question": question, "docs": [d for _, d in pairs]})
    resp.raise_for_status()
    scores = resp.json()["scores"]
    return list(zip([t for t, _ in pairs], [float(s) for s in scores]))


def embed_query(question: str) -> np.ndarray:
    return embed_texts([question])[0]


def rebuild_index(docs: list[dict]) -> int:
    """清空并按 {table, doc} 列表重建 Chroma 索引（seed_metadata.py 调用）。

    BM25 索引无需重建（按 app.db mtime 惰性构建，元数据变更后自动失效）。
    """
    client = _client or chromadb.PersistentClient(path=str(settings.chroma_dir_file))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    if not docs:
        return 0
    embeddings = embed_texts([d["doc"] for d in docs])
    collection.add(
        ids=[d["table"] for d in docs],
        embeddings=embeddings.tolist(),
        documents=[d["doc"] for d in docs],
        metadatas=[{"table": d["table"]} for d in docs],
    )
    return len(docs)


# ---- 召回三路 ----

def _vector_hits(collection, qvec: np.ndarray, k: int) -> list[tuple[str, float]]:
    """向量路：返回 [(表名, 相似度)]（已过滤阈值）。"""
    res = collection.query(
        query_embeddings=[qvec.tolist()],
        n_results=min(k, collection.count()),
        include=["metadatas", "distances"],
    )
    hits: list[tuple[str, float]] = []
    for metas, dist in zip(res["metadatas"][0], res["distances"][0]):
        score = 1.0 - float(dist)  # cosine distance → similarity
        if score >= settings.rag_score_threshold:
            hits.append((metas["table"], score))
    return hits


def _get_bm25():
    """BM25 索引（jieba 分词，TTL 惰性重建——PG 无文件 mtime，语义元数据变更后按 TTL 收敛）。"""
    global _bm25_cache
    import time

    if time.time() - _bm25_cache["ts"] > settings.schema_cache_ttl:
        tables = semantic_meta.load_tables()
        docs = [semantic_meta.build_index_doc(t) for t in tables.values()]
        tokenized = [jieba.lcut(d.lower()) for d in docs]
        _bm25_cache = {
            "ts": time.time(),
            "bm25": BM25Okapi(tokenized),
            "table_names": [t.table for t in tables.values()],
        }
        logger.info("BM25 索引已构建：%d 篇文档", len(tokenized))
    return _bm25_cache


def _bm25_hits(question: str, k: int) -> list[tuple[str, float]]:
    """BM25 路：返回 [(表名, 归一化分数)]。"""
    cache = _get_bm25()
    scores = cache["bm25"].get_scores(jieba.lcut(question.lower()))
    ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
    max_score = float(max(scores)) if scores.size else 1.0
    return [
        (cache["table_names"][i], float(scores[i]) / max_score)
        for i in ranked[:k]
        if scores[i] > 0
    ]


def _keyword_hits(question: str, tables: dict[str, semantic_meta.TableMeta]) -> list[tuple[str, float]]:
    """关键词路：业务名（表名/字段业务名）直接出现在提问中即命中。"""
    q = question.lower()
    hits: list[tuple[str, float]] = []
    for name, t in tables.items():
        needles = [t.table.lower(), t.biz_name] + [c["biz_name"] for c in t.columns]
        needles = [n for n in needles if n and len(n) >= 2]  # 单字/空串太泛
        if any(n in q for n in needles):
            hits.append((name, 1.0))
    return hits


# ---- RRF 融合与重排序 ----

def rrf_fuse(*rank_maps: dict[str, int]) -> list[tuple[str, float]]:
    """RRF 融合：score = Σ 1/(k + rank + 1)，按分数降序。"""
    scores: dict[str, float] = {}
    for rm in rank_maps:
        for table, rank in rm.items():
            scores[table] = scores.get(table, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def _rerank(question: str, pairs: list[tuple[str, str]]) -> list[tuple[str, float]] | None:
    """交叉编码器重排序：返回 [(表名, 分数)]；模型不可用时返回 None（跳过）。"""
    if settings.model_service_url:
        return _remote_rerank(question, pairs)
    model = get_reranker()
    raw = model.predict([[question, doc] for _, doc in pairs])
    return list(zip([t for t, _ in pairs], [float(s) for s in raw]))


def retrieve_tables(question: str) -> list[str]:
    """双路召回 + RRF 融合 + 重排序 + JOIN 闭包；空列表 = 未命中（调用方兜底全量）。"""
    tables = semantic_meta.load_tables()
    if not tables:
        logger.warning("语义元数据为空，请先运行 scripts/seed_metadata.py")
        return []
    collection = get_collection()
    k = settings.rag_candidate_k

    # ---- 1~3. 三路召回 ----
    dense_rank: dict[str, int] = {}
    if collection.count() > 0:
        try:
            hits = _vector_hits(collection, embed_query(question), k)
            for i, (t, _s) in enumerate(hits):
                dense_rank.setdefault(t, i)
        except Exception as e:
            logger.warning("向量召回失败（自动降级）: %s", e)

    bm25_rank: dict[str, int] = {}
    if settings.rag_bm25_enabled:
        try:
            hits = _bm25_hits(question, k)
            for i, (t, _s) in enumerate(hits):
                bm25_rank.setdefault(t, i)
        except Exception as e:
            logger.warning("BM25 召回失败（自动降级）: %s", e)

    kw_rank: dict[str, int] = {}
    if settings.rag_keyword_boost:
        for t, _s in _keyword_hits(question, tables):
            kw_rank[t] = 0  # 精确命中视为最高优先级

    # ---- 4. RRF 融合 ----
    fused = rrf_fuse(dense_rank, bm25_rank, kw_rank)
    if not fused:
        logger.info("三路均未命中")
        return []

    order = [t for t, _ in fused]

    # ---- 5. 交叉编码器重排序 ----
    if settings.rag_rerank_enabled and len(order) > 1:
        pool = order[: settings.rag_top_k]
        try:
            docs = {t: semantic_meta.build_index_doc(tables[t]) for t in pool if t in tables}
            scores = _rerank(question, [(t, docs[t]) for t in pool if t in docs])
        except Exception as e:
            logger.warning("重排序失败（回退 RRF 排序）: %s", e)
            scores = None
        if scores:
            kept = [(t, s) for t, s in scores if s >= settings.rag_rerank_threshold]
            if kept:
                order = [t for t, _ in sorted(kept, key=lambda x: -x[1])]
            else:
                logger.info("重排后全部低于阈值 %.2f，回退 RRF 排序", settings.rag_rerank_threshold)

    # ---- 6~7. JOIN 闭包 + 上限裁剪 ----
    selected = list(order)
    for name in list(selected):
        for nb in sorted(semantic_meta.relation_neighbors(tables, name)):
            if nb not in selected and nb in tables:
                selected.append(nb)
    selected = selected[: settings.rag_max_tables]
    logger.info("RAG 召回 %d 张表: %s（提问: %s）", len(selected), selected, question[:40])
    return selected
