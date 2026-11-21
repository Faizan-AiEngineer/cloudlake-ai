from contextlib import contextmanager
from pathlib import Path
from threading import Timer

import duckdb

from data_engineering.schema import FEEDS

FACT_SALES = """
SELECT i.order_item_id, o.order_id, o.customer_id, p.product_id,
       CAST(o.order_timestamp AS DATE) AS sale_date, o.order_status, o.shipping_region,
       c.country, c.customer_segment, c.acquisition_channel, p.category, p.product_name,
       i.quantity, o.currency,
       CAST(i.quantity * i.unit_price * r.usd_per_unit AS DECIMAL(20,2)) AS gross_usd,
       CAST(i.discount * r.usd_per_unit AS DECIMAL(20,2)) AS discount_usd,
       CAST(i.tax * r.usd_per_unit AS DECIMAL(20,2)) AS tax_usd,
       CASE WHEN o.order_status = 'completed'
            THEN CAST((i.line_total - i.tax) * r.usd_per_unit AS DECIMAL(20,2)) ELSE 0 END AS revenue_usd,
       CASE WHEN o.order_status = 'returned'
            THEN CAST((i.line_total - i.tax) * r.usd_per_unit AS DECIMAL(20,2)) ELSE 0 END AS refunds_usd,
       CASE WHEN o.order_status = 'completed'
            THEN CAST(i.quantity * p.unit_cost AS DECIMAL(20,2)) ELSE 0 END AS cost_usd
FROM order_items i JOIN orders o USING(order_id)
JOIN products p USING(product_id) JOIN customers c USING(customer_id)
JOIN rates r USING(currency)
"""

MODELS = {
    "dim_customer": "SELECT * FROM customers",
    "dim_product": "SELECT * FROM products",
    "dim_date": """
        SELECT DISTINCT CAST(order_timestamp AS DATE) AS date, month(order_timestamp) AS month,
          year(order_timestamp) AS year, dayofweek(order_timestamp) AS weekday FROM orders
    """,
    "dim_region": "SELECT DISTINCT shipping_region FROM orders",
    "dim_channel": "SELECT DISTINCT acquisition_channel FROM customers",
    "dim_payment_method": "SELECT DISTINCT payment_method FROM orders",
    "fact_sales": FACT_SALES,
    "fact_orders": """
        SELECT o.*, c.country, c.customer_segment, c.acquisition_channel,
          COALESCE(s.revenue_usd, 0) AS revenue_usd, COALESCE(s.refunds_usd, 0) AS refunds_usd
        FROM orders o JOIN customers c USING(customer_id)
        LEFT JOIN (SELECT order_id, SUM(revenue_usd) revenue_usd, SUM(refunds_usd) refunds_usd
                   FROM fact_sales GROUP BY order_id) s USING(order_id)
    """,
    "fact_payments": """
        SELECT p.*, o.currency, CAST(p.transaction_amount * r.usd_per_unit AS DECIMAL(20,2)) AS amount_usd
        FROM payments p JOIN orders o USING(order_id) JOIN rates r USING(currency)
    """,
    "fact_inventory": "SELECT i.*, p.category, p.current_stock FROM inventory i JOIN products p USING(product_id)",
    "fact_clickstream": """
        SELECT e.*, p.category, c.country, c.customer_segment FROM clickstream e
        JOIN products p USING(product_id) JOIN customers c USING(customer_id)
    """,
    "daily_sales": """
        SELECT sale_date, SUM(revenue_usd) AS revenue_usd,
          SUM(revenue_usd-cost_usd) AS gross_profit_usd,
          count(DISTINCT order_id) FILTER (WHERE order_status='completed') AS orders
        FROM fact_sales GROUP BY sale_date ORDER BY sale_date
    """,
    "monthly_sales": """
        SELECT CAST(date_trunc('month', sale_date) AS DATE) AS month, SUM(revenue_usd) AS revenue_usd,
          SUM(refunds_usd) AS refunds_usd FROM fact_sales GROUP BY 1 ORDER BY 1
    """,
    "product_profitability": """
        SELECT product_id, any_value(product_name) AS product_name, SUM(revenue_usd) AS revenue_usd,
          SUM(revenue_usd-cost_usd) AS gross_profit_usd
        FROM fact_sales GROUP BY product_id ORDER BY revenue_usd DESC
    """,
    "customer_value": """
        SELECT customer_id, count(DISTINCT order_id) AS orders, SUM(revenue_usd) AS lifetime_value_proxy
        FROM fact_sales WHERE order_status='completed' GROUP BY customer_id
    """,
    "customer_segmentation": """
        SELECT c.customer_segment, count(*) AS customers, COALESCE(SUM(v.lifetime_value_proxy),0) AS revenue_usd
        FROM customers c LEFT JOIN customer_value v USING(customer_id) GROUP BY c.customer_segment
    """,
    "regional_performance": """
        SELECT shipping_region, SUM(revenue_usd) AS revenue_usd, SUM(refunds_usd) AS refunds_usd
        FROM fact_sales GROUP BY shipping_region
    """,
    "marketing_performance": """
        SELECT acquisition_channel, SUM(revenue_usd) AS revenue_usd, count(DISTINCT customer_id) AS customers
        FROM fact_sales GROUP BY acquisition_channel
    """,
    "inventory_performance": """
        SELECT product_id, any_value(current_stock) AS current_stock, SUM(quantity_change) AS net_movement,
          SUM(-quantity_change) FILTER (WHERE event_type='sale') / nullif(any_value(current_stock),0)
            AS turnover_proxy
        FROM fact_inventory GROUP BY product_id
    """,
    "payment_success": """
        SELECT payment_method, count(*) AS attempts,
          count(*) FILTER (WHERE payment_status IN ('captured','refunded')) / count(*) AS success_rate
        FROM fact_payments GROUP BY payment_method
    """,
    "conversion_funnel": """
        SELECT event_type, count(DISTINCT session_id) AS sessions FROM fact_clickstream GROUP BY event_type
    """,
    "returns_cancellations": """
        SELECT order_status, count(*) AS orders, SUM(refunds_usd) AS refunds_usd
        FROM fact_orders GROUP BY order_status
    """,
    "revenue_growth": """
        SELECT c.month, c.revenue_usd,
          c.revenue_usd / nullif(m.revenue_usd,0) - 1 AS month_over_month,
          c.revenue_usd / nullif(y.revenue_usd,0) - 1 AS year_over_year
        FROM monthly_sales c LEFT JOIN monthly_sales m ON m.month = c.month - interval '1 month'
        LEFT JOIN monthly_sales y ON y.month = c.month - interval '1 year'
        ORDER BY c.month
    """,
}

FILTERS = {
    "start": "sale_date >= CAST(? AS DATE)", "end": "sale_date <= CAST(? AS DATE)",
    "country": "country = ?", "region": "shipping_region = ?", "category": "category = ?",
    "segment": "customer_segment = ?", "channel": "acquisition_channel = ?",
}


def records(cursor):
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def build(silver: Path, gold: Path):
    gold.mkdir(parents=True, exist_ok=True)
    tables = {}
    with duckdb.connect(config={"threads": 2}) as conn:
        for dataset in FEEDS:
            conn.read_parquet(str(silver / f"{dataset}.parquet")).create_view(dataset)
        for name, sql in MODELS.items():
            path = gold / f"{name}.parquet"
            model = conn.sql(sql)
            model.write_parquet(str(path), compression="zstd")
            parquet = conn.read_parquet(str(path))
            count = parquet.count("*").fetchone()[0]
            tables[name] = {"rows": count, "bytes": path.stat().st_size}
            parquet.create_view(name)
    return tables


@contextmanager
def analytical_connection(directory, timeout=8):
    with duckdb.connect(config={
        "threads": 2, "memory_limit": "256MB", "autoinstall_known_extensions": "false",
        "autoload_known_extensions": "false",
    }) as connection:
        connection.execute("SET allowed_directories = ?", [[str(directory.resolve())]])
        connection.execute("SET enable_external_access = false")
        timer = Timer(timeout, connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            yield connection
        finally:
            timer.cancel()
            timer.join()


def sales_summary(gold, filters):
    where = [sql for key, sql in FILTERS.items() if filters.get(key) is not None]
    values = [filters[key] for key in FILTERS if filters.get(key) is not None]
    filtered = "SELECT * FROM fact_sales" + (" WHERE " + " AND ".join(where) if where else "")
    with analytical_connection(gold) as connection:
        connection.read_parquet(str(gold / "fact_sales.parquet")).create_view("fact_sales")
        connection.execute("CREATE TEMP TABLE filtered AS " + filtered, values)
        kpis = records(connection.execute("""
            WITH customers AS (
                SELECT customer_id, count(DISTINCT order_id) orders FROM filtered
                WHERE order_status='completed' GROUP BY customer_id
            )
            SELECT coalesce(sum(revenue_usd),0) AS revenue_usd,
              coalesce(sum(revenue_usd-cost_usd),0) AS gross_profit_usd,
              sum(revenue_usd-cost_usd) / nullif(sum(revenue_usd),0) AS gross_margin,
              coalesce(sum(refunds_usd),0) AS refunds_usd,
              count(DISTINCT order_id) FILTER (WHERE order_status='completed') AS orders,
              sum(revenue_usd) / nullif(count(DISTINCT order_id) FILTER (WHERE order_status='completed'),0)
                AS average_order_value,
              coalesce(sum(quantity) FILTER (WHERE order_status='completed'),0) AS units,
              (SELECT count(*) FROM customers) AS customers,
              (SELECT count(*) FILTER (WHERE orders>1) / nullif(count(*),0) FROM customers) AS repeat_rate,
              count(DISTINCT order_id) FILTER(WHERE order_status='returned') / nullif(count(DISTINCT order_id),0)
                AS return_rate
            FROM filtered
        """))[0]
        trend = records(connection.execute("""
            SELECT CAST(date_trunc('month', sale_date) AS DATE) AS month, sum(revenue_usd) AS revenue_usd
            FROM filtered GROUP BY 1 ORDER BY 1 LIMIT 120
        """))
        categories = records(connection.execute("""
            SELECT category, sum(revenue_usd) AS revenue_usd, sum(revenue_usd-cost_usd) AS gross_profit_usd
            FROM filtered GROUP BY category ORDER BY revenue_usd DESC LIMIT 100
        """))
        regions = records(connection.execute("""
            SELECT shipping_region, sum(revenue_usd) AS revenue_usd
            FROM filtered GROUP BY shipping_region ORDER BY revenue_usd DESC LIMIT 100
        """))
        channels = records(connection.execute("""
            SELECT acquisition_channel, sum(revenue_usd) AS revenue_usd
            FROM filtered GROUP BY acquisition_channel ORDER BY revenue_usd DESC LIMIT 100
        """))
        return {"kpis": kpis, "trend": trend, "categories": categories, "regions": regions, "channels": channels}
