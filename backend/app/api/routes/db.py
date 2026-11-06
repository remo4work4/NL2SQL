"""表结构浏览接口（FR-13，Phase 9 PG）。"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_username
from app.core.database import connect_business_db
from app.schemas.api import TableInfo

router = APIRouter(
    prefix="/api/db",
    tags=["db"],
    dependencies=[Depends(get_current_username)],
)


@router.get("/schema", response_model=list[TableInfo])
def get_schema():
    conn = connect_business_db()
    try:
        tables = [
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
            ).fetchall()
        ]
        out = []
        for table in tables:
            info = conn.execute(
                "SELECT column_name AS name, data_type AS type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                (table,),
            ).fetchall()
            out.append(
                TableInfo(
                    table=table,
                    columns=[{"name": r["name"], "type": r["type"]} for r in info],
                    row_count=conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"],
                )
            )
        return out
    finally:
        conn.close()
