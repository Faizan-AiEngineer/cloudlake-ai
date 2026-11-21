import sys
from datetime import UTC, datetime
from pathlib import PurePosixPath

import boto3
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from data_engineering.rules import RULES, validate_records
from data_engineering.schema import FEEDS, PROCESSING_ORDER

ALLOWED = {".csv", ".json", ".parquet"}


def sources(bucket, name):
    paginator = boto3.client("s3").get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"landing/{name}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            suffix = PurePosixPath(key).suffix.lower()
            if suffix in ALLOWED:
                yield suffix, f"s3a://{bucket}/{key}"


def bronze(spark, bucket, name, run_id):
    frames = []
    for suffix, uri in sources(bucket, name):
        if suffix == ".parquet":
            raw = spark.read.parquet(uri)
        elif suffix == ".csv":
            raw = spark.read.option("header", True).csv(uri)
        else:
            raw = spark.read.option("multiLine", True).json(uri)
        fields = [F.col("`" + col.replace("`", "``") + "`").cast("string").alias(col) for col in sorted(raw.columns)]
        payload = F.to_json(F.struct(*fields), options={"ignoreNullFields": "false"})
        frames.append(raw.select(payload.alias("payload")).select(
            "payload", F.lit(datetime.now(UTC).isoformat()).alias("ingestion_timestamp"),
            F.lit(name).alias("source_name"), F.lit(uri).alias("source_file"),
            F.lit(run_id).alias("ingestion_run_id"), F.lit("1").alias("schema_version"),
            F.sha2("payload", 256).alias("record_hash"), F.monotonically_increasing_id().alias("record_number"),
        ))
    if not frames:
        raise ValueError(f"Missing required source feed {name}")
    combined, *rest = frames
    for frame in rest:
        combined = combined.unionByName(frame)
    return combined


def write_table(data, database, name):
    data.writeTo(f"lake.{database}.{name}").using("iceberg").tableProperty("format-version", "2").createOrReplace()


def main():
    args = getResolvedOptions(sys.argv, ["JOB_RUN_ID", "LAKE_BUCKET", "CATALOG_DB", "QUALITY_LIMIT"])
    bucket, database, run_id = args["LAKE_BUCKET"], args["CATALOG_DB"], args["JOB_RUN_ID"]
    threshold = float(args["QUALITY_LIMIT"])
    spark = (SparkSession.builder
             .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
             .config("spark.sql.catalog.lake.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
             .config("spark.sql.catalog.lake.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
             .config("spark.sql.catalog.lake.warehouse", f"s3://{bucket}/gold/")
             .config("spark.sql.session.timeZone", "UTC")
             .getOrCreate())
    valid = {}
    blocked = []
    root = f"s3a://{bucket}"
    for name in PROCESSING_ORDER:
        feed = FEEDS[name]
        raw = bronze(spark, bucket, name, run_id)
        raw.write.mode("overwrite").parquet(f"{root}/bronze/{run_id}/{name}")
        checks = validate_records(name, raw, valid).persist()
        try:
            total = checks.count()
            counts = checks.select(F.explode("_violations").alias("rule")).groupBy("rule").count().collect()
            blocked.extend(f"{name}.{row.rule}" for row in counts
                           if RULES[row.rule][1] == "CRITICAL" and row["count"] > total * threshold)
            critical_rules = [rule for rule, (_, severity) in RULES.items() if severity != "INFO"]
            hard_failure = F.arrays_overlap("_violations", F.array(*[F.lit(rule) for rule in critical_rules]))
            checks.filter(hard_failure).select(
                "payload", "source_file", "record_hash", "_violations",
            ).write.mode("overwrite").parquet(f"{root}/quarantine/{run_id}/{name}")
            location = f"{root}/silver/{run_id}/{name}"
            checks.filter(~hard_failure).select(*feed.fields).write.mode("overwrite").parquet(location)
            valid[name] = spark.read.parquet(location)
        finally:
            checks.unpersist()
    if blocked:
        raise ValueError("Critical quality gate blocked Gold: " + ", ".join(blocked))
    for name, frame in valid.items():
        frame.createOrReplaceTempView(name)
    sales = spark.sql("""
      SELECT i.order_item_id, o.order_id, CAST(o.order_timestamp AS DATE) AS sale_date,
             c.country, p.category, o.order_status,
             CASE WHEN o.order_status='completed'
               THEN CAST((i.line_total-i.tax)*r.usd_per_unit AS DECIMAL(20,2)) ELSE 0 END AS revenue_usd
      FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id)
      JOIN products p USING(product_id) JOIN rates r USING(currency)
    """)
    write_table(sales, database, "fact_sales")
    write_table(sales.groupBy("sale_date").agg(F.sum("revenue_usd").alias("revenue_usd")), database, "daily_sales")


if __name__ == "__main__":
    main()
