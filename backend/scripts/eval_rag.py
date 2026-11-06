"""Phase 6（双路+RRF+重排版）验收脚本：附录 A 的 10 条标准问句做 RAG 召回评估。

前置：已运行 scripts/seed_metadata.py（app.db 有语义元数据 + Chroma 索引），
且 backend/models/ 下已有 bge-m3 与 bge-reranker-v2-m3。
用法（在 backend/ 目录下）：
    .venv/Scripts/python scripts/eval_rag.py

验收标准：
- 召回命中率：预期表 ⊆ 召回表，10/10 ≥ 90%（硬指标）
- 首表命中率：第一张召回表与问句主主题一致（排序质量，参考指标 ≥ 90%）
- 检索延迟：单问全链路（稠密+BM25+RRF+重排+闭包）≤ 3s
- 注入比：平均注入表数 / 全量表数（演示库表少+闭包 ≈ 全量，仅记录）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 允许脚本独立运行（import app）

from app.core import retriever, semantic_meta
from app.core.config import settings

APPENDIX_A_EXPECTED = {
    "2025 年各月销售额趋势": {"orders"},
    "各品类销售额占比": {"orders", "products"},
    "销售额最高的 10 个商品": {"orders", "products"},
    "各地区销售额对比": {"orders", "customers"},
    "2025 年第三季度订单量": {"orders"},
    "客单价最高的城市 Top5": {"orders", "customers"},
    "各客户等级的平均消费金额": {"orders", "customers"},
    "2025 年同比增长最快的品类": {"orders", "products"},
    "2025 年 6 月每天的下单数": {"orders"},
    "全量数据的总销售额和总订单数": {"orders"},
}

# 每问的主主题表（用于评估 RRF+重排后的排序质量）
APPENDIX_A_PRIMARY = {
    "2025 年各月销售额趋势": "orders",
    "各品类销售额占比": "products",
    "销售额最高的 10 个商品": "products",
    "各地区销售额对比": "customers",
    "2025 年第三季度订单量": "orders",
    "客单价最高的城市 Top5": "customers",
    "各客户等级的平均消费金额": "customers",
    "2025 年同比增长最快的品类": "products",
    "2025 年 6 月每天的下单数": "orders",
    "全量数据的总销售额和总订单数": "orders",
}


def main() -> int:
    if not settings.rag_enabled:
        print("[提示] RAG_ENABLED=false，本脚本仅评估检索器本身", file=sys.stderr)
    tables = semantic_meta.load_tables()
    if not tables:
        print("[错误] 语义元数据为空，先运行 scripts/seed_metadata.py", file=sys.stderr)
        return 1

    # 预加载模型，不把加载时间计入延迟
    retriever.get_embedder()
    if settings.rag_rerank_enabled:
        try:
            retriever.get_reranker()
        except Exception as e:
            print(f"[提示] 重排模型不可用（{e}），本评估退化为无重排模式")

    total_tables = len(tables)
    print(f"全量表数: {total_tables}；BM25={settings.rag_bm25_enabled}，重排={settings.rag_rerank_enabled}")
    print(f"{'问句':<26} {'召回表（按序）':<44} {'首表':<10} {'命中':<4} {'耗时':<8}")
    print("-" * 110)

    hit = 0
    primary_hit = 0
    sum_ratio = 0.0
    sum_lat = 0.0
    for question, expected in APPENDIX_A_EXPECTED.items():
        t0 = time.perf_counter()
        selected = retriever.retrieve_tables(question)
        lat = time.perf_counter() - t0
        ok = expected.issubset(set(selected))
        phit = bool(selected) and selected[0] == APPENDIX_A_PRIMARY[question]
        hit += ok
        primary_hit += phit
        sum_ratio += len(selected) / total_tables
        sum_lat += lat
        print(f"{question:<26} {','.join(selected):<44} {selected[0] if selected else '-':<10} {'✓' if ok else '✗':<4} {lat*1000:>6.0f}ms")

    n = len(APPENDIX_A_EXPECTED)
    print("-" * 110)
    print(f"召回命中率: {hit}/{n}（{hit/n*100:.0f}%，标准 ≥90%）")
    print(f"首表命中率: {primary_hit}/{n}（{primary_hit/n*100:.0f}%，参考 ≥90%，反映 RRF+重排排序质量）")
    print(f"平均注入比: {sum_ratio/n:.2f}（演示库表少+JOIN闭包≈全量，规模增大后下降）")
    print(f"平均检索延迟: {sum_lat/n*1000:.0f}ms（标准 ≤3s，含稠密+BM25+RRF+重排）")
    return 0 if hit / n >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
