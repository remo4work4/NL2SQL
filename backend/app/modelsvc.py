"""模型服务（Phase 9 多实例）：独立进程持有一份 BGE 稠密 + 交叉编码器模型。

多实例部署时各 API 实例通过 HTTP 调用本服务（MODEL_SERVICE_URL 配置），
避免每实例重复加载 fp32 模型（16GB 机器上两份即 OOM，Phase 8 实测）。

启动（backend/ 目录下）：
    .venv/Scripts/python -m uvicorn app.modelsvc:app --port 8004

接口：
    GET  /health → {"status": "ok"}
    POST /embed  {"texts": [...]} → {"vectors": [[...], ...]}
    POST /rerank {"question": "...", "docs": [...]} → {"scores": [...]}
"""
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.core.config import settings

app = FastAPI(title="NL2SQL 模型服务", version="0.1.0")

_embedder: SentenceTransformer | None = None
_reranker: CrossEncoder | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        model_dir = settings.bge_model_dir_file
        path = str(model_dir) if (model_dir / "config.json").exists() else settings.bge_model
        _embedder = SentenceTransformer(path)
    return _embedder


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        model_dir = settings.reranker_model_dir_file
        path = str(model_dir) if (model_dir / "config.json").exists() else settings.reranker_model
        _reranker = CrossEncoder(path)
    return _reranker


class EmbedRequest(BaseModel):
    texts: list[str]


class RerankRequest(BaseModel):
    question: str
    docs: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "embedder": _embedder is not None, "reranker": _reranker is not None}


@app.post("/embed")
def embed(body: EmbedRequest) -> dict:
    model = _get_embedder()
    vectors = model.encode(body.texts, normalize_embeddings=True)
    return {"vectors": np.asarray(vectors).tolist()}


@app.post("/rerank")
def rerank(body: RerankRequest) -> dict:
    model = _get_reranker()
    scores = model.predict([[body.question, d] for d in body.docs])
    return {"scores": [float(s) for s in scores]}
