"""SQL 安全校验测试（FR-3，附录 B 用例必须全部拦截）。"""
import pytest

from app.core.sql_safety import SQLUnsafeError, execute_query, validate_sql

# ---- 附录 B：必须全部拦截 ----
APPENDIX_B = [
    "SELECT * FROM customers; DROP TABLE orders",
    "DELETE FROM orders WHERE id > 0",
    "UPDATE products SET unit_price = 0",
    "INSERT INTO customers (name, city, region, level) VALUES ('x', 'y', 'z', '普通')",
    "ATTACH DATABASE 'evil.db' AS x; SELECT * FROM x.t",
]


@pytest.mark.parametrize("sql", APPENDIX_B)
def test_appendix_b_all_blocked(sql):
    with pytest.raises(SQLUnsafeError):
        validate_sql(sql)


def test_valid_select_passes():
    sql = validate_sql("SELECT region, SUM(amount) FROM orders GROUP BY region")
    assert "LIMIT" in sql


def test_with_cte_passes():
    sql = validate_sql(
        "WITH t AS (SELECT customer_id, SUM(amount) AS s FROM orders GROUP BY customer_id) "
        "SELECT * FROM t WHERE s > 100 ORDER BY s DESC"
    )
    assert sql.startswith("WITH")


def test_recursive_cte_blocked():
    """递归 CTE 计算炸弹拦截。"""
    with pytest.raises(SQLUnsafeError):
        validate_sql(
            "WITH RECURSIVE cnt(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM cnt WHERE x < 1e9) "
            "SELECT count(*) FROM cnt"
        )


def test_multi_statement_blocked():
    with pytest.raises(SQLUnsafeError):
        validate_sql("SELECT 1; SELECT 2")


def test_write_keyword_in_string_literal_allowed():
    """字符串字面量中的禁用词不应误伤。"""
    sql = validate_sql("SELECT * FROM products WHERE name LIKE '%update%'")
    assert "LIMIT" in sql


def test_existing_limit_not_duplicated():
    sql = validate_sql("SELECT * FROM orders LIMIT 10")
    assert sql.count("LIMIT") == 1


def test_comments_stripped():
    sql = validate_sql("-- 这是注释\nSELECT * FROM orders")
    assert sql.startswith("SELECT")


def test_empty_sql_blocked():
    with pytest.raises(SQLUnsafeError):
        validate_sql("   ")


def test_execute_query_returns_result(db_paths):
    result = execute_query("SELECT COUNT(*) AS c FROM orders", max_rows=500)
    assert result["columns"] == ["c"]
    assert result["rows"][0][0] == 300
    assert result["truncated"] is False


def test_execute_query_truncates(db_paths):
    result = execute_query("SELECT * FROM orders", max_rows=10)
    assert len(result["rows"]) == 10
    assert result["truncated"] is True


def test_execute_query_error(db_paths):
    from app.core.sql_safety import SQLExecutionError
    with pytest.raises(SQLExecutionError):
        execute_query("SELECT * FROM no_such_table")


def test_execute_query_timeout(db_paths):
    """大交叉连接 + 极小超时 → 抛超时错误（FR-4 执行超时兜底，PG statement_timeout）。"""
    sql = "SELECT COUNT(*) FROM orders a, orders b, orders c"  # 300^3 行
    with pytest.raises(Exception, match="超时"):
        execute_query(sql, max_rows=10, timeout=0.02)


def test_business_db_is_readonly(db_paths):
    """只读角色兜底：写操作在 PG 权限层被拒绝（nl2sql_ro 仅 SELECT 授权）。"""
    import psycopg

    from app.core.database import connect_business_db

    conn = connect_business_db()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO products (name, category, unit_price) VALUES ('x','y',1)")
    conn.close()
