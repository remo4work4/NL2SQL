"""Phase 6 RAG 检索与语义元数据测试。

embedding 用确定性假向量（关键词词典 one-hot），不加载真实 BGE 模型；
真实 BGE + Chroma 的端到端验证在 scripts/eval_rag.py（验收脚本）。
"""
import numpy as np
import pytest

from app.agent.prompts import build_schema_digest, build_table_detail
from app.core import retriever, semantic_meta
from app.core.config import settings
from app.core.database import connect_business_db
from app.services import chat_service

# 假向量词典：文档与提问按包含的关键词 one-hot + L2 归一化
LEXICON = ["订单", "销售额", "客户", "商品", "品类", "地区", "金额", "日期", "等级"]


def fake_vec(text: str) -> np.ndarray:
    v = np.array([1.0 if w in text else 0.0 for w in LEXICON])
    norm = float(np.linalg.norm(v)) or 1.0
    return v / norm


@pytest.fixture()
def meta_tables() -> list[semantic_meta.TableMeta]:
    """与 seed_business 业务库一致的语义元数据（含关系）。"""
    return [
        semantic_meta.TableMeta(
            table="customers", biz_name="客户", description="客户主数据，含地区与等级维度",
            columns=[
                {"column": "id", "biz_name": "客户ID", "description": "主键", "enum_values": []},
                {"column": "name", "biz_name": "客户名称", "description": "客户姓名", "enum_values": []},
                {"column": "city", "biz_name": "城市", "description": "所在城市", "enum_values": []},
                {"column": "region", "biz_name": "地区", "description": "所在大区", "enum_values": ["华东", "华北", "华南", "西南", "华中", "东北"]},
                {"column": "level", "biz_name": "客户等级", "description": "会员等级", "enum_values": ["普通", "银牌", "金牌"]},
            ],
        ),
        semantic_meta.TableMeta(
            table="products", biz_name="商品", description="商品主数据，含品类维度",
            columns=[
                {"column": "id", "biz_name": "商品ID", "description": "主键", "enum_values": []},
                {"column": "name", "biz_name": "商品名称", "description": "商品名", "enum_values": []},
                {"column": "category", "biz_name": "品类", "description": "商品品类", "enum_values": ["数码家电", "服饰鞋包", "食品生鲜", "家居日用", "美妆个护"]},
                {"column": "unit_price", "biz_name": "单价", "description": "商品单价，单位元", "enum_values": []},
            ],
        ),
        semantic_meta.TableMeta(
            table="orders", biz_name="订单", description="订单行级明细，销售额来源",
            columns=[
                {"column": "id", "biz_name": "订单ID", "description": "主键", "enum_values": []},
                {"column": "order_date", "biz_name": "下单日期", "description": "下单日期，YYYY-MM-DD 文本", "enum_values": []},
                {"column": "customer_id", "biz_name": "客户ID", "description": "外键", "enum_values": []},
                {"column": "product_id", "biz_name": "商品ID", "description": "外键", "enum_values": []},
                {"column": "quantity", "biz_name": "数量", "description": "购买数量", "enum_values": []},
                {"column": "amount", "biz_name": "销售金额", "description": "该行销售额，单位元", "enum_values": []},
            ],
            relations=[
                {"from_column": "customer_id", "to_table": "customers", "to_column": "id", "description": "订单归属客户"},
                {"from_column": "product_id", "to_table": "products", "to_column": "id", "description": "订单对应商品"},
            ],
        ),
    ]


@pytest.fixture()
def rag_index(db_paths, meta_tables, tmp_path, monkeypatch):
    """在临时目录建 Chroma 索引（假向量）并种子语义元数据。

    稠密路用假向量（词典 one-hot）；BM25 路用真实 jieba+rank_bm25（轻量）；
    重排序打桩为 None（跳过，避免加载交叉编码器模型）。
    """
    monkeypatch.setattr(settings, "chroma_mode", "embedded")  # 测试用临时嵌入式索引（.env 为 server）
    monkeypatch.setattr(settings, "chroma_dir", str(tmp_path / "chroma"))
    monkeypatch.setattr(retriever, "_client", None)
    monkeypatch.setattr(retriever, "_bm25_cache", {"ts": 0.0, "bm25": None, "table_names": []})
    monkeypatch.setattr(retriever, "embed_query", lambda q: fake_vec(q))
    monkeypatch.setattr(retriever, "_rerank", lambda q, pairs: None)
    semantic_meta.upsert_metadata(meta_tables)
    col = retriever.get_collection()
    docs = {t.table: semantic_meta.build_index_doc(t) for t in meta_tables}
    col.add(
        ids=list(docs),
        embeddings=[fake_vec(d).tolist() for d in docs.values()],
        documents=list(docs.values()),
        metadatas=[{"table": t} for t in docs],
    )
    return col


class TestSemanticMeta:
    def test_roundtrip(self, db_paths, meta_tables):
        semantic_meta.upsert_metadata(meta_tables)
        loaded = semantic_meta.load_tables()
        assert set(loaded) == {"customers", "products", "orders"}
        assert loaded["customers"].biz_name == "客户"
        assert loaded["customers"].column_map["level"]["enum_values"] == ["普通", "银牌", "金牌"]
        assert loaded["orders"].neighbor_tables == {"customers", "products"}

    def test_neighbors_both_directions(self, db_paths, meta_tables):
        semantic_meta.upsert_metadata(meta_tables)
        loaded = semantic_meta.load_tables()
        # customers 是 orders 的入边目标，也应当回指 orders
        assert semantic_meta.relation_neighbors(loaded, "customers") == {"orders"}

    def test_index_doc_contains_biz_and_enum(self, meta_tables):
        doc = semantic_meta.build_index_doc(meta_tables[0])
        assert "客户" in doc and "region" in doc
        assert "普通/银牌/金牌" in doc

    def test_overwrite_replaces(self, db_paths, meta_tables):
        semantic_meta.upsert_metadata(meta_tables)
        semantic_meta.upsert_metadata([])
        assert semantic_meta.load_tables() == {}


class TestDigestWithMeta:
    def test_table_detail_has_biz_annotation(self, db_paths, meta_tables):
        semantic_meta.upsert_metadata(meta_tables)
        conn = connect_business_db()
        try:
            detail = build_table_detail(conn, "orders", semantic_meta.load_tables()["orders"])
        finally:
            conn.close()
        assert "表 orders（订单）" in detail
        assert "销售金额" in detail
        assert "取值仅限" not in detail  # orders 无枚举字段
        assert "customer_id → customers.id" in detail  # 关系注入

    def test_customers_detail_has_enums(self, db_paths, meta_tables):
        semantic_meta.upsert_metadata(meta_tables)
        conn = connect_business_db()
        try:
            detail = build_table_detail(conn, "customers", semantic_meta.load_tables()["customers"])
        finally:
            conn.close()
        assert "取值仅限：普通/银牌/金牌" in detail

    def test_digest_selection(self, db_paths, meta_tables):
        semantic_meta.upsert_metadata(meta_tables)
        conn = connect_business_db()
        try:
            selected = build_schema_digest(conn, tables=["orders"])
            full = build_schema_digest(conn)
        finally:
            conn.close()
        assert "表 orders（" in selected
        assert "表 customers（" not in selected
        assert "表 customers（" in full and "表 products（" in full


class TestRetriever:
    def test_vector_plus_keyword(self, rag_index):
        # 向量命中 customers/orders（金额/客户/等级共享），关键词兜底补命中
        selected = retriever.retrieve_tables("各客户等级的平均消费金额")
        assert "customers" in selected and "orders" in selected
        # 分数排序：customers 相似度最高，应排第一
        assert selected[0] == "customers"

    def test_join_closure(self, rag_index):
        # 只问销售额 → 命中 orders → 闭包带出 customers/products
        selected = retriever.retrieve_tables("2025 年各月销售额趋势")
        assert "orders" in selected
        assert "customers" in selected and "products" in selected

    def test_empty_fallback(self, rag_index):
        # 全零向量 + 无关键词 → 未命中 → 空列表（调用方兜底全量注入）
        assert retriever.retrieve_tables("这是一个无关问题") == []

    def test_cap(self, rag_index, monkeypatch):
        monkeypatch.setattr(settings, "rag_max_tables", 2)
        selected = retriever.retrieve_tables("2025 年各月销售额趋势")
        assert len(selected) <= 2


class TestRRFAndRerank:
    def test_rrf_fuse_math(self):
        fused = retriever.rrf_fuse(
            {"orders": 0, "products": 1},
            {"products": 0, "customers": 2},
        )
        # products = 1/61 + 1/62 > orders = 1/61 > customers = 1/63
        assert [t for t, _ in fused] == ["products", "orders", "customers"]

    def test_bm25_real_smoke(self, rag_index):
        """真实 jieba + rank_bm25：客户等级问句应命中 customers。"""
        hits = retriever._bm25_hits("各客户等级的平均消费金额", k=3)
        assert hits and hits[0][0] == "customers"

    def test_bm25_path_contributes_to_fusion(self, rag_index, monkeypatch):
        """稠密路只中 orders、BM25 路只中 products → 融合后两者都在。"""
        monkeypatch.setattr(retriever, "_vector_hits", lambda c, qv, k: [("orders", 0.9)])
        monkeypatch.setattr(retriever, "_bm25_hits", lambda q, k: [("products", 0.8)])
        selected = retriever.retrieve_tables("某问题")
        assert "orders" in selected and "products" in selected

    def test_rerank_reorders(self, rag_index, monkeypatch):
        """交叉编码器分数翻转 RRF 顺序。"""
        monkeypatch.setattr(retriever, "_vector_hits", lambda c, qv, k: [("orders", 0.9), ("products", 0.7)])
        monkeypatch.setattr(retriever, "_bm25_hits", lambda q, k: [])
        monkeypatch.setattr(
            retriever, "_rerank",
            lambda q, pairs: [(t, 9.9 if t == "products" else 0.1) for t, _ in pairs],
        )
        selected = retriever.retrieve_tables("某问题")
        assert selected[0] == "products"

    def test_rerank_threshold_fallback_to_rrf(self, rag_index, monkeypatch):
        """重排后全部低于阈值 → 回退 RRF 排序（不因重排丢表）。"""
        monkeypatch.setattr(retriever, "_vector_hits", lambda c, qv, k: [("orders", 0.9), ("products", 0.7)])
        monkeypatch.setattr(retriever, "_bm25_hits", lambda q, k: [])
        monkeypatch.setattr(retriever, "_rerank", lambda q, pairs: [(t, -5.0) for t, _ in pairs])
        selected = retriever.retrieve_tables("某问题")
        assert selected[0] == "orders"


class TestChatServiceIntegration:
    def test_rag_digest_selected(self, db_paths, meta_tables, monkeypatch):
        semantic_meta.upsert_metadata(meta_tables)
        monkeypatch.setattr(retriever, "retrieve_tables", lambda q: ["orders"])
        chat_service._schema_cache["mtime"] = 0.0
        digest, full = chat_service._get_schema_digests("任意问题")
        assert "表 orders（" in digest
        assert "表 customers（" not in digest
        assert "表 customers（" in full

    def test_rag_miss_equals_full(self, db_paths, meta_tables, monkeypatch):
        semantic_meta.upsert_metadata(meta_tables)
        monkeypatch.setattr(retriever, "retrieve_tables", lambda q: [])
        chat_service._schema_cache["mtime"] = 0.0
        digest, full = chat_service._get_schema_digests("任意问题")
        assert digest == full

    def test_rag_disabled_equals_full(self, db_paths, meta_tables, monkeypatch):
        semantic_meta.upsert_metadata(meta_tables)
        monkeypatch.setattr(settings, "rag_enabled", False)
        monkeypatch.setattr(retriever, "retrieve_tables", lambda q: ["orders"])  # 不应被调用
        chat_service._schema_cache["mtime"] = 0.0
        digest, full = chat_service._get_schema_digests("任意问题")
        assert digest == full
