from dataclasses import dataclass
from graphlib import TopologicalSorter


@dataclass(frozen=True)
class Feed:
    key: str
    fields: dict[str, str]
    timestamp: str | None = None
    references: tuple[tuple[str, str], ...] = ()


FEEDS = {
    "customers": Feed("customer_id", dict(
        customer_id="string", registration_date="date", country="string", city="string",
        age_group="string", customer_segment="string", acquisition_channel="string", account_status="string",
    ), "registration_date"),
    "products": Feed("product_id", dict(
        product_id="string", product_name="string", category="string", subcategory="string",
        brand="string", supplier_id="string", unit_cost="decimal(18,2)", selling_price="decimal(18,2)",
        current_stock="int", product_status="string",
    )),
    "orders": Feed("order_id", dict(
        order_id="string", customer_id="string", order_timestamp="timestamp", order_status="string",
        currency="string", payment_method="string", shipping_region="string",
    ), "order_timestamp", (("customer_id", "customers"), ("currency", "rates"))),
    "order_items": Feed("order_item_id", dict(
        order_item_id="string", order_id="string", product_id="string", quantity="int",
        unit_price="decimal(18,2)", discount="decimal(18,2)", tax="decimal(18,2)", line_total="decimal(18,2)",
    ), references=(("order_id", "orders"), ("product_id", "products"))),
    "payments": Feed("payment_id", dict(
        payment_id="string", order_id="string", payment_timestamp="timestamp", payment_status="string",
        transaction_amount="decimal(18,2)", payment_method="string",
    ), "payment_timestamp", (("order_id", "orders"),)),
    "inventory": Feed("event_id", dict(
        event_id="string", product_id="string", event_timestamp="timestamp", event_type="string",
        quantity_change="int", warehouse_id="string",
    ), "event_timestamp", (("product_id", "products"),)),
    "clickstream": Feed("event_id", dict(
        event_id="string", session_id="string", customer_id="string", timestamp="timestamp",
        event_type="string", product_id="string", device_type="string", traffic_source="string",
    ), "timestamp", (("customer_id", "customers"), ("product_id", "products"))),
    "customer_activity": Feed("event_id", dict(
        event_id="string", customer_id="string", timestamp="timestamp", activity_type="string",
    ), "timestamp", (("customer_id", "customers"),)),
    "rates": Feed("currency", dict(currency="string", usd_per_unit="decimal(12,6)", provenance="string")),
}

# Schema v1 permits additive source payloads in Bronze. Silver quarantines unknown or missing fields.
SCHEMA_VERSION = "1"
PROCESSING_ORDER = tuple(TopologicalSorter({
    name: {parent for _, parent in feed.references} for name, feed in FEEDS.items()
}).static_order())
