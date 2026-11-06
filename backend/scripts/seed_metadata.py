"""Phase 6：把已人工复核的语义元数据写入 app.db 并重建 Chroma 向量索引。

流程：data/metadata.draft.json（Qwen 生成）→ 人工复核 → data/metadata.json → 本脚本。
业务库 schema 变更后：重新跑 generate_metadata.py + 复核 + 本脚本。

用法（在 backend/ 目录下）：
    .venv/Scripts/python scripts/seed_metadata.py                # 默认 data/metadata.json
    .venv/Scripts/python scripts/seed_metadata.py --file data/metadata.draft.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 允许脚本独立运行（import app）

from pydantic import ValidationError

from app.core import database, retriever, semantic_meta
from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="写入语义元数据并重建向量索引")
    parser.add_argument("--file", type=Path, default=settings.metadata_file_path)
    args = parser.parse_args()

    if not args.file.exists():
        print(f"[错误] {args.file} 不存在。先运行 scripts/generate_metadata.py 生成草稿并人工复核", file=sys.stderr)
        return 1

    try:
        meta_file = semantic_meta.MetadataFile.model_validate(json.loads(args.file.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"[错误] {args.file} 校验失败：{e}", file=sys.stderr)
        return 1

    tables = []
    for t in meta_file.tables:
        tables.append(
            semantic_meta.TableMeta(
                table=t.table,
                biz_name=t.name,
                description=t.description,
                columns=[
                    {
                        "column": c.column, "biz_name": c.name,
                        "description": c.description, "enum_values": c.enum_values,
                    }
                    for c in t.columns
                ],
                relations=[
                    {
                        "from_column": r.from_column, "to_table": r.to_table,
                        "to_column": r.to_column, "description": r.description,
                    }
                    for r in t.relations
                ],
            )
        )

    # 0. 确保元数据表存在（幂等建表 + 预置管理员）
    database.init_app_db()

    # 1. 写入 PG（语义治理的持久层）
    semantic_meta.upsert_metadata(tables)
    print(f"[1/2] 语义元数据已写入 PostgreSQL：{semantic_meta.meta_summary()}")

    # 2. 重建 Chroma 向量索引（首次会加载/下载 BGE 模型）
    docs = [{"table": t.table, "doc": semantic_meta.build_index_doc(t)} for t in tables]
    t0 = time.perf_counter()
    n = retriever.rebuild_index(docs)
    print(f"[2/2] Chroma 索引已重建：{n} 条文档 → {settings.chroma_dir_file}（耗时 {time.perf_counter() - t0:.1f}s）")
    print("完成。重启后端后提问即可走 RAG 检索注入（不重启也可生效，schema 缓存按 mtime 重建）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
