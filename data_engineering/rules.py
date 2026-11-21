from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql.types import MapType, StringType

from data_engineering.schema import FEEDS

RULES = {
    "completeness": ("Required fields", "CRITICAL"),
    "uniqueness": ("Latest record per business key", "WARNING"),
    "validity": ("Data types and valid values", "CRITICAL"),
    "referential_integrity": ("Registered foreign keys", "CRITICAL"),
    "schema": ("Registered source fields", "CRITICAL"),
    "consistency": ("Financial arithmetic", "CRITICAL"),
    "business": ("Business domain constraints", "CRITICAL"),
    "freshness": ("Arrival older than prior watermark", "INFO"),
}

def expression_for_business(dataset):
    col = F.col
    return {
        "customers": col("account_status").isin("active", "inactive"),
        "products": (col("unit_cost") >= 0) & (col("selling_price") >= 0) & (col("current_stock") >= 0),
        "orders": col("order_status").isin("completed", "returned", "cancelled"),
        "order_items": (col("quantity") > 0) & (col("unit_price") >= 0) & (col("discount") >= 0)
        & (col("discount") <= col("quantity") * col("unit_price")) & (col("tax") >= 0),
        "payments": col("payment_status").isin("captured", "refunded", "failed") & (col("transaction_amount") >= 0),
        "inventory": col("event_type").isin("receipt", "sale", "return", "adjustment") & (col("quantity_change") != 0),
        "clickstream": col("event_type").isin("view", "cart", "checkout", "purchase"),
        "customer_activity": col("activity_type").isin("login", "search", "wishlist", "return_request"),
        "rates": col("usd_per_unit") > 0,
    }[dataset]


def validate_records(dataset, raw, parents, watermark=None, run_id=None):
    feed = FEEDS[dataset]
    mapping = MapType(StringType(), StringType())
    parsed = raw.withColumn("_map", F.from_json("payload", mapping))
    fields = [
        F.expr(f"try_cast(element_at(_map, '{field}') AS {typ})").alias(field)
        for field, typ in feed.fields.items()
    ]
    frame = parsed.select("*", *fields)
    expected = F.array(*[F.lit(field) for field in feed.fields])
    same_keys = (F.size(F.array_except(F.map_keys("_map"), expected)) == 0) & (
        F.size(F.array_except(expected, F.map_keys("_map"))) == 0
    )
    missing = F.lit(False)
    invalid = F.lit(False)
    for field in feed.fields:
        value = F.element_at("_map", F.lit(field))
        missing = missing | value.isNull() | (F.trim(value) == "")
        invalid = invalid | (value.isNotNull() & F.col(field).isNull())
    window = Window.partitionBy(feed.key).orderBy(
        F.desc("ingestion_timestamp"), F.desc("source_file"), F.desc("record_number"), F.desc("record_hash"),
    )
    eligible = F.col(feed.key).isNotNull()
    duplicate = eligible & (F.row_number().over(window) > 1)
    frame = frame.withColumn("_duplicate", duplicate)
    bad_reference = F.lit(False)
    for foreign_key, parent in feed.references:
        registered = f"_registered_{foreign_key}"
        keys = parents[parent].select(F.col(FEEDS[parent].key).alias(registered))
        frame = frame.join(keys, frame[foreign_key] == keys[registered], "left")
        bad_reference = bad_reference | (F.col(foreign_key).isNotNull() & F.col(registered).isNull())
    inconsistent = F.lit(False)
    if dataset == "order_items":
        balance = F.col("quantity") * F.col("unit_price") - F.col("discount") + F.col("tax")
        inconsistent = F.abs(F.col("line_total") - balance) > F.lit(0.005)
    late = F.lit(False)
    if watermark and feed.timestamp:
        late = (F.col("ingestion_run_id") == run_id) & (
            F.col(feed.timestamp).cast("timestamp") < F.to_timestamp(F.lit(watermark))
        )
    failed = {
        "completeness": missing, "uniqueness": F.col("_duplicate"), "validity": invalid,
        "referential_integrity": bad_reference, "schema": ~same_keys, "consistency": inconsistent,
        "business": ~expression_for_business(dataset), "freshness": late,
    }
    violations = F.array_compact(F.array(*[F.when(check, F.lit(rule)) for rule, check in failed.items()]))
    return frame.select(*feed.fields, "payload", "source_file", "record_hash", violations.alias("_violations"))
