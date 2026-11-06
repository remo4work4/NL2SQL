"""生成业务示例库（销售主题，需求文档 6.1 节）。

Phase 9：默认写入 PostgreSQL（--engine pg，多实例共享业务数据）；
--engine sqlite 保留（历史调试用，应用已不读取 SQLite 业务库）。

用法（在 backend/ 目录下）：
    .venv/Scripts/python scripts/seed_business.py                # PG 默认规模
    .venv/Scripts/python scripts/seed_business.py --orders 5200 --force
    .venv/Scripts/python scripts/seed_business.py --engine sqlite

表结构：
    customers(id, name, city, region, level)
    products(id, name, category, unit_price)
    orders(id, order_date, customer_id, product_id, quantity, amount)
"""
import argparse
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 允许脚本独立运行（import app）

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "business.db"

REGIONS: dict[str, list[str]] = {
    "华东": ["上海", "杭州", "南京", "苏州"],
    "华北": ["北京", "天津", "石家庄"],
    "华南": ["广州", "深圳", "厦门"],
    "西南": ["成都", "重庆", "昆明"],
    "华中": ["武汉", "长沙", "郑州"],
    "东北": ["沈阳", "大连", "哈尔滨"],
}

LEVELS = ["普通", "普通", "普通", "银牌", "银牌", "金牌"]  # 加权分布

PRODUCTS: dict[str, list[str]] = {
    "数码家电": ["无线耳机", "智能手表", "蓝牙音箱", "平板电脑", "智能台灯", "电动牙刷", "扫地机器人", "咖啡机", "路由器", "移动电源"],
    "服饰鞋包": ["运动鞋", "牛仔裤", "羽绒服", "T恤", "衬衫", "双肩包", "连衣裙", "卫衣", "风衣", "皮带"],
    "食品生鲜": ["坚果礼盒", "牛奶", "大米", "橄榄油", "咖啡豆", "蜂蜜", "茶叶", "巧克力", "红酒", "海鲜礼盒"],
    "家居日用": ["四件套", "收纳箱", "香薰蜡烛", "保温杯", "浴巾", "拖把", "垃圾桶", "衣架", "地毯", "加湿器"],
    "美妆个护": ["面霜", "精华液", "口红", "防晒霜", "洗发水", "香水", "面膜", "粉底液", "身体乳", "剃须刀"],
}

PRICE_RANGE: dict[str, tuple[float, float]] = {
    "数码家电": (99, 4999),
    "服饰鞋包": (59, 899),
    "食品生鲜": (20, 500),
    "家居日用": (15, 300),
    "美妆个护": (30, 800),
}

# 季节性权重：11/12 月大促偏高，2 月偏低
_MONTH_WEIGHT = {1: 1.0, 2: 0.8, 3: 1.0, 4: 1.0, 5: 1.05, 6: 1.1, 7: 1.0, 8: 1.0, 9: 1.0, 10: 1.05, 11: 1.3, 12: 1.4}


def seed_business(
    db_path: Path,
    n_customers: int = 100,
    n_products: int = 50,
    n_orders: int = 5200,
    start: date = date(2024, 1, 1),
    end: date = date(2025, 12, 31),
    random_seed: int = 42,
    engine: str = "pg",
) -> dict:
    """生成业务数据。engine: pg（PostgreSQL，默认）| sqlite（历史）。"""
    random.seed(random_seed)

    # ---- 数据生成（与存储引擎无关）----
    region_list = list(REGIONS.keys())
    customers = []
    for i in range(n_customers):
        region = region_list[i % len(region_list)]
        cities = REGIONS[region]
        city = cities[i % len(cities)]
        level = LEVELS[i % len(LEVELS)]
        customers.append((f"客户{i + 1:03d}", city, region, level))

    categories = list(PRODUCTS.keys())
    products = []
    for i in range(n_products):
        category = categories[i % len(categories)]
        names = PRODUCTS[category]
        name = names[(i // len(categories)) % len(names)]
        lo, hi = PRICE_RANGE[category]
        unit_price = round(random.uniform(lo, hi), 2)
        products.append((name, category, unit_price))

    days: list[tuple[date, float]] = []
    d = start
    while d <= end:
        days.append((d, _MONTH_WEIGHT[d.month]))
        d += timedelta(days=1)
    dates = [x[0] for x in days]
    weights = [x[1] for x in days]

    orders = []
    for _ in range(n_orders):
        order_date = random.choices(dates, weights=weights, k=1)[0]
        customer_id = random.randint(1, n_customers)
        product_id = random.randint(1, n_products)
        unit_price = products[product_id - 1][2]
        quantity = random.randint(1, 5)
        amount = round(unit_price * quantity * random.uniform(0.9, 1.1), 2)
        orders.append((order_date.isoformat(), customer_id, product_id, quantity, amount))

    if engine == "pg":
        return _seed_pg(customers, products, orders)
    return _seed_sqlite(db_path, customers, products, orders)


def _seed_pg(customers, products, orders) -> dict:
    """写入 PostgreSQL（多实例共享业务数据）。"""
    import psycopg
    from psycopg.rows import dict_row

    from app.core.config import settings

    conn = psycopg.connect(settings.pg_dsn, row_factory=dict_row)
    try:
        conn.execute("DROP TABLE IF EXISTS orders")
        conn.execute("DROP TABLE IF EXISTS customers")
        conn.execute("DROP TABLE IF EXISTS products")
        conn.execute(
            "CREATE TABLE customers ("
            "id SERIAL PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL,"
            "region TEXT NOT NULL, level TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE products ("
            "id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,"
            "unit_price DOUBLE PRECISION NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE orders ("
            "id SERIAL PRIMARY KEY, order_date TEXT NOT NULL, customer_id INTEGER NOT NULL,"
            "product_id INTEGER NOT NULL, quantity INTEGER NOT NULL,"
            "amount DOUBLE PRECISION NOT NULL)"
        )
        conn.execute("CREATE INDEX idx_orders_date ON orders(order_date)")
        conn.execute("CREATE INDEX idx_orders_customer ON orders(customer_id)")
        conn.execute("CREATE INDEX idx_orders_product ON orders(product_id)")
        conn.execute("GRANT SELECT ON customers, products, orders TO nl2sql_ro")
        _insert_pg(conn, "INSERT INTO customers (name, city, region, level) VALUES (%s, %s, %s, %s)", customers)
        _insert_pg(conn, "INSERT INTO products (name, category, unit_price) VALUES (%s, %s, %s)", products)
        _insert_pg(
            conn,
            "INSERT INTO orders (order_date, customer_id, product_id, quantity, amount) VALUES (%s, %s, %s, %s, %s)",
            orders,
        )
        conn.commit()

        stats = {
            "customers": conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"],
            "products": conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"],
            "orders": conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"],
            "total_amount": conn.execute("SELECT ROUND(SUM(amount)::numeric, 2) AS s FROM orders").fetchone()["s"],
            "date_range": tuple(
                conn.execute("SELECT MIN(order_date) AS a, MAX(order_date) AS b FROM orders").fetchone().values()
            ),
            "categories": conn.execute("SELECT COUNT(DISTINCT category) AS n FROM products").fetchone()["n"],
        }
        return stats
    finally:
        conn.close()


def _insert_pg(conn, sql: str, rows: list[tuple]) -> None:
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def _seed_sqlite(db_path: Path, customers, products, orders) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            DROP TABLE IF EXISTS orders;
            DROP TABLE IF EXISTS customers;
            DROP TABLE IF EXISTS products;
            CREATE TABLE customers (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL,
              city TEXT NOT NULL, region TEXT NOT NULL, level TEXT NOT NULL
            );
            CREATE TABLE products (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL,
              category TEXT NOT NULL, unit_price REAL NOT NULL
            );
            CREATE TABLE orders (
              id INTEGER PRIMARY KEY, order_date TEXT NOT NULL,
              customer_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
              quantity INTEGER NOT NULL, amount REAL NOT NULL
            );
            CREATE INDEX idx_orders_date ON orders(order_date);
            CREATE INDEX idx_orders_customer ON orders(customer_id);
            CREATE INDEX idx_orders_product ON orders(product_id);
            """
        )
        conn.executemany(
            "INSERT INTO customers (name, city, region, level) VALUES (?, ?, ?, ?)", customers
        )
        conn.executemany(
            "INSERT INTO products (name, category, unit_price) VALUES (?, ?, ?)", products
        )
        conn.executemany(
            "INSERT INTO orders (order_date, customer_id, product_id, quantity, amount) VALUES (?, ?, ?, ?, ?)",
            orders,
        )
        conn.commit()
        stats = {
            "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "total_amount": conn.execute("SELECT ROUND(SUM(amount), 2) FROM orders").fetchone()[0],
            "date_range": tuple(
                conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
            ),
            "categories": conn.execute("SELECT COUNT(DISTINCT category) FROM products").fetchone()[0],
        }
        return stats
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成业务示例库（默认 PostgreSQL）")
    parser.add_argument("--customers", type=int, default=100)
    parser.add_argument("--products", type=int, default=50)
    parser.add_argument("--orders", type=int, default=5200)
    parser.add_argument("--engine", choices=["pg", "sqlite"], default="pg")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true", help="覆盖已有数据")
    args = parser.parse_args()

    if args.engine == "sqlite" and args.db.exists() and not args.force:
        print(f"[跳过] {args.db} 已存在，使用 --force 覆盖")
        return 0

    stats = seed_business(args.db, args.customers, args.products, args.orders, engine=args.engine)
    target = "PostgreSQL（多实例共享）" if args.engine == "pg" else str(args.db)
    print(f"[完成] {target}")
    print(f"  客户 {stats['customers']} 条 / 商品 {stats['products']} 条（{stats['categories']} 品类）/ 订单 {stats['orders']} 条")
    print(f"  时间范围 {stats['date_range'][0]} ~ {stats['date_range'][1]}，总销售额 {stats['total_amount']:,.2f} 元")
    return 0


if __name__ == "__main__":
    sys.exit(main())
