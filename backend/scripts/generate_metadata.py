"""Phase 6：用 Qwen 生成语义元数据草稿（人工复核后由 seed_metadata.py 写入）。

产物：data/metadata.draft.json —— 请人工逐条复核业务名/描述/枚举/关联，
确认无误后复制（或重命名）为 data/metadata.json 再运行 seed_metadata.py。

用法（在 backend/ 目录下）：
    .venv/Scripts/python scripts/generate_metadata.py            # 输出到默认草稿路径
    .venv/Scripts/python scripts/generate_metadata.py --out data/metadata.draft.json --force

设计说明：
- 输入 = 物理 schema + 各 TEXT 字段的去重取值样本（供判断枚举）+ 样例行
- 输出 = metadata.json 结构（pydantic 校验，缺表/缺字段会告警）
- 表多时单次调用会超上下文，迭代项：按表分批生成后合并
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 允许脚本独立运行（import app）

from pydantic import ValidationError

from app.core.config import settings
from app.core.database import connect_business_db
from app.core.semantic_meta import MetadataFile
from app.llm.qwen import get_chat_model

MAX_DISTINCT = 30  # 去重取值超过此数的字段视为自由文本，不供枚举样本

SYSTEM_PROMPT = """你是数据仓库的元数据管理员。根据给定的业务库物理结构（SQLite），生成中文语义元数据 JSON。

要求：
1. 每个表给出 name（简短中文业务名，≤6 字）与 description（一句话说明表主题与粒度）。
2. 每个字段给出 name（中文业务名）与 description（一句话业务含义，含单位/格式说明，如"金额，单位元"）。
3. enum_values 只对取值有限的枚举字段填写完整合法取值（如客户等级），自由文本/日期/数值留空数组 []。
4. relations 从字段名与取值样本推断主外键关联：from_column 是当前表字段，to_table/to_column 是目标表主键（如 orders.customer_id → customers.id）；无关联的字段不写。
5. 必须覆盖给定结构中的全部表与全部字段，不得遗漏或编造不存在的表/字段。
6. 只输出一个 JSON 对象，格式：{"version": 1, "tables": [{"table": "表名", "name": "中文名", "description": "描述", "columns": [{"column": "字段名", "name": "中文名", "description": "描述", "enum_values": []}], "relations": [{"from_column": "字段", "to_table": "表", "to_column": "字段", "description": "关联说明"}]}]}，不要任何多余文字。"""


def _collect_schema(conn) -> dict:
    """收集物理结构与枚举候选样本（PG information_schema）。"""
    tables = [
        row["table_name"]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]
    out = {"tables": []}
    for table in tables:
        info = conn.execute(
            "SELECT column_name AS name, data_type AS type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            (table,),
        ).fetchall()
        cols = []
        for r in info:
            col = {"name": r["name"], "type": r["type"], "distinct_sample": None}
            if r["type"] in ("text", "character varying", "varchar"):
                values = [
                    list(v.values())[0]
                    for v in conn.execute(
                        f'SELECT DISTINCT "{r["name"]}" AS v FROM "{table}" ORDER BY 1 LIMIT {MAX_DISTINCT + 1}'
                    ).fetchall()
                ]
                if len(values) <= MAX_DISTINCT:
                    col["distinct_sample"] = values
            cols.append(col)
        samples = [
            ", ".join(f"{k}={v}" for k, v in row.items())
            for row in conn.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
        ]
        out["tables"].append(
            {
                "table": table,
                "row_count": conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"],
                "columns": cols,
                "samples": samples,
            }
        )
    return out


def generate(schema: dict, out: Path, force: bool = False) -> int:
    if out.exists() and not force:
        print(f"[跳过] {out} 已存在，使用 --force 覆盖（避免覆盖已复核内容）")
        return 0
    if not settings.dashscope_api_key:
        print("[错误] 未配置 DASHSCOPE_API_KEY（backend/.env）", file=sys.stderr)
        return 1

    llm = get_chat_model(json_mode=True)
    user_prompt = (
        "业务库结构如下（JSON）：\n" + json.dumps(schema, ensure_ascii=False, indent=2) + "\n\n请按要求生成语义元数据 JSON。"
    )
    resp = llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    text = str(resp.content).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            print("[错误] 模型输出不是 JSON：\n" + text[:500], file=sys.stderr)
            return 1
        data = json.loads(text[start : end + 1])

    try:
        meta = MetadataFile.model_validate(data)
    except ValidationError as e:
        print("[错误] 模型输出未通过校验：", e, file=sys.stderr)
        return 1

    # 覆盖度检查：表/字段必须与物理结构一致
    db_tables = {t["table"] for t in schema["tables"]}
    gen_tables = {t.table for t in meta.tables}
    missing_tables = db_tables - gen_tables
    extra_tables = gen_tables - db_tables
    missing_cols: list[str] = []
    for t in meta.tables:
        db_cols = {c["name"] for c in next(x for x in schema["tables"] if x["table"] == t.table)["columns"]}
        gen_cols = {c.column for c in t.columns}
        missing_cols += [f"{t.table}.{c}" for c in db_cols - gen_cols]
    if missing_tables or extra_tables or missing_cols:
        print(
            f"[告警] 覆盖度不完整：缺表 {sorted(missing_tables) or '无'} / 多表 {sorted(extra_tables) or '无'} / 缺字段 {missing_cols}，请复核后补全"
        )

    # 枚举完备性检查：低基数 TEXT 字段的去重取值应与 enum_values 一致
    schema_by_table = {t["table"]: t for t in schema["tables"]}
    enum_warnings: list[str] = []
    for t in meta.tables:
        for c in t.columns:
            db_col = next(
                (x for x in schema_by_table[t.table]["columns"] if x["name"] == c.column), None
            )
            if db_col and db_col["distinct_sample"] is not None:
                db_vals = set(db_col["distinct_sample"])
                gen_vals = set(c.enum_values)
                if db_vals - gen_vals:
                    enum_warnings.append(f"{t.table}.{c.column} 缺枚举值: {sorted(db_vals - gen_vals)}")
                if gen_vals - db_vals:
                    enum_warnings.append(f"{t.table}.{c.column} 含库中不存在的枚举值: {sorted(gen_vals - db_vals)}")
    if enum_warnings:
        print("[告警] 枚举值不完备，请复核补全：")
        for w in enum_warnings[:20]:
            print(f"  - {w}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(meta.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    n_cols = sum(len(t.columns) for t in meta.tables)
    n_rel = sum(len(t.relations) for t in meta.tables)
    print(f"[完成] 草稿已写入 {out}：{len(meta.tables)} 张表 / {n_cols} 个字段 / {n_rel} 条关系")
    print("下一步：人工复核后保存为 data/metadata.json，运行 scripts/seed_metadata.py 生效")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Qwen 生成语义元数据草稿")
    parser.add_argument("--out", type=Path, default=settings.metadata_draft_file_path)
    parser.add_argument("--force", action="store_true", help="覆盖已有草稿")
    args = parser.parse_args()

    conn = connect_business_db()
    try:
        schema = _collect_schema(conn)
    finally:
        conn.close()
    print(f"[输入] 业务库 {settings.business_db_file}：{len(schema['tables'])} 张表")
    return generate(schema, args.out, args.force)


if __name__ == "__main__":
    sys.exit(main())
