"""语义元数据层（Phase 6，Phase 9 迁 PostgreSQL）：表/字段业务描述、枚举值、表关系。

存储于 PostgreSQL（table_meta / column_meta / table_relations），
由 scripts/seed_metadata.py 从已人工复核的 data/metadata.json 写入；
草稿由 scripts/generate_metadata.py 用 Qwen 生成。

RAG 检索（retriever.py）与 schema 摘要注入（prompts.py）都以这里为准。
"""
import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.core.database import connect_db


class ColumnMetaIn(BaseModel):
    """metadata.json 中的字段条目（seed 输入校验）。"""
    column: str
    name: str
    description: str
    enum_values: list[str] = []


class RelationIn(BaseModel):
    """metadata.json 中的关联条目。"""
    from_column: str
    to_table: str
    to_column: str
    description: str = ""


class TableMetaIn(BaseModel):
    """metadata.json 中的表条目。"""
    table: str
    name: str
    description: str
    columns: list[ColumnMetaIn]
    relations: list[RelationIn] = []


class MetadataFile(BaseModel):
    """metadata.json 整体结构（seed 输入校验）。"""
    version: int = 1
    tables: list[TableMetaIn]


@dataclass
class TableMeta:
    """运行时视图：单表完整语义元数据。"""
    table: str
    biz_name: str
    description: str
    columns: list[dict] = field(default_factory=list)  # {column, biz_name, description, enum_values}
    relations: list[dict] = field(default_factory=list)  # {from_column, to_table, to_column, description}

    @property
    def column_map(self) -> dict[str, dict]:
        return {c["column"]: c for c in self.columns}

    @property
    def neighbor_tables(self) -> set[str]:
        """一跳关联表（外键闭包用）：出边。"""
        return {r["to_table"] for r in self.relations}


def upsert_metadata(tables: list[TableMeta]) -> None:
    """把语义元数据整体写入 PG（全量替换，与 metadata.json 保持一致）。"""
    conn = connect_db()
    try:
        now = _now()
        conn.execute("DELETE FROM table_relations")
        conn.execute("DELETE FROM column_meta")
        conn.execute("DELETE FROM table_meta")
        for t in tables:
            conn.execute(
                "INSERT INTO table_meta (table_name, biz_name, description, updated_at) VALUES (%s, %s, %s, %s)",
                (t.table, t.biz_name, t.description, now),
            )
            for c in t.columns:
                conn.execute(
                    "INSERT INTO column_meta (table_name, column_name, biz_name, description, enum_values, updated_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (t.table, c["column"], c["biz_name"], c["description"],
                     json.dumps(c.get("enum_values") or [], ensure_ascii=False), now),
                )
            for r in t.relations:
                conn.execute(
                    "INSERT INTO table_relations (from_table, from_column, to_table, to_column, description)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    (t.table, r["from_column"], r["to_table"], r["to_column"], r.get("description", "")),
                )
        conn.commit()
    finally:
        conn.close()


def load_tables() -> dict[str, TableMeta]:
    """从 PG 读全部语义元数据（无则返回空 dict）。"""
    conn = connect_db()
    try:
        tables: dict[str, TableMeta] = {}
        for row in conn.execute("SELECT table_name, biz_name, description FROM table_meta").fetchall():
            tables[row["table_name"]] = TableMeta(table=row["table_name"], biz_name=row["biz_name"], description=row["description"])
        for row in conn.execute("SELECT table_name, column_name, biz_name, description, enum_values FROM column_meta").fetchall():
            t = tables.get(row["table_name"])
            if t:
                t.columns.append({
                    "column": row["column_name"], "biz_name": row["biz_name"],
                    "description": row["description"],
                    "enum_values": json.loads(row["enum_values"] or "[]"),
                })
        for row in conn.execute(
            "SELECT from_table, from_column, to_table, to_column, description FROM table_relations"
        ).fetchall():
            t = tables.get(row["from_table"])
            if t:
                t.relations.append({
                    "from_column": row["from_column"], "to_table": row["to_table"],
                    "to_column": row["to_column"], "description": row["description"],
                })
        return tables
    finally:
        conn.close()


def relation_neighbors(tables: dict[str, TableMeta], table: str) -> set[str]:
    """JOIN 闭包：该表一跳可达的关联表（出边 + 入边）。"""
    out = set(tables[table].neighbor_tables) if table in tables else set()
    for name, t in tables.items():
        if any(r["to_table"] == table for r in t.relations):
            out.add(name)
    return out


def build_index_doc(t: TableMeta) -> str:
    """单表的向量化文档（Chroma 索引与注入共用同一份文本）。"""
    cols = []
    for c in t.columns:
        enum = f"（取值仅限：{'/'.join(c['enum_values'])}）" if c.get("enum_values") else ""
        cols.append(f"{c['column']}（{c['biz_name']}）：{c['description']}{enum}")
    rel = ""
    if t.relations:
        rel = "；关联：" + "、".join(
            f"{r['from_column']} 对应 {r['to_table']}.{r['to_column']}" for r in t.relations
        )
    return f"表 {t.table}（{t.biz_name}）：{t.description}。字段：{'；'.join(cols)}{rel}"


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def meta_summary() -> str:
    """元数据概览（seed 脚本输出用）。"""
    tables = load_tables()
    n_cols = sum(len(t.columns) for t in tables.values())
    n_rel = sum(len(t.relations) for t in tables.values())
    return f"{len(tables)} 张表 / {n_cols} 个字段 / {n_rel} 条关系"
