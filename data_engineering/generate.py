import csv
import json
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from data_engineering.schema import FEEDS

PROFILES = {"tiny": 1_000, "demo": 10_000, "standard": 100_000, "large": 1_000_000}
FIXTURE = Path(__file__).resolve().parents[1] / "sample_data" / "rates.json"
GEOGRAPHIES = [
    ("US", "Chicago", "North America", "USD"), ("US", "Seattle", "North America", "USD"),
    ("DE", "Berlin", "Europe", "EUR"), ("FR", "Paris", "Europe", "EUR"),
    ("GB", "London", "Europe", "GBP"),
]
CHANNELS = ["Organic", "Search", "Referral", "Email", "Social"]
CATEGORIES = {"Electronics": ("Audio", "Accessories"), "Home": ("Kitchen", "Lighting"),
              "Outdoor": ("Camping", "Fitness"), "Office": ("Stationery", "Furniture")}
METHODS = ["Card", "Wallet", "Bank transfer"]
START = datetime(2024, 1, 1, tzinfo=UTC)


def money(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def generate(profile="demo", seed=42, batch=0, counts=None):
    rng = random.Random(seed)
    activity = random.Random(f"{seed}:{batch}")
    target = PROFILES[profile]
    sizing = {
        "customers": max(10, target // 10), "products": max(5, target // 40),
        "orders": max(5, target // 7), "inventory": target // 12,
        "clickstream": target // 4, "customer_activity": target // 18,
    }
    for key, value in (counts or {}).items():
        if key not in {*sizing, "order_items", "payments"} or value < 1:
            raise ValueError(f"Invalid adjustable count for {key}")
        sizing[key] = value
    rates = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data = {name: [] for name in FEEDS}
    data["rates"] = rates

    def event_time():
        day = activity.randrange(731)
        date = START + timedelta(days=day)
        if date.month not in (11, 12) and activity.random() < 0.28:
            date = START.replace(year=date.year, month=11, day=1) + timedelta(days=activity.randrange(60))
        return (date + timedelta(hours=activity.randrange(24), minutes=activity.randrange(60), days=batch)).isoformat()

    for i in range(sizing["customers"]):
        country, city, _, _ = rng.choice(GEOGRAPHIES)
        data["customers"].append(dict(
            customer_id=f"C{i:06}", country=country, city=city,
            registration_date=(START - timedelta(days=rng.randrange(1, 800))).date().isoformat(),
            age_group=rng.choice(["18–24", "25–34", "35–49", "50+"]),
            customer_segment=rng.choices(["Consumer", "Premium", "Small business"], [65, 23, 12])[0],
            acquisition_channel=rng.choice(CHANNELS), account_status=rng.choices(["active", "inactive"], [91, 9])[0],
        ))
    prices = {}
    for i in range(sizing["products"]):
        category = rng.choice(list(CATEGORIES))
        subcategory = rng.choice(CATEGORIES[category])
        cost = rng.randrange(450, 32_000)
        price = cost * rng.randrange(130, 270) // 100
        product_id = f"P{i:05}"
        prices[product_id] = price
        data["products"].append(dict(
            product_id=product_id, product_name=f"{subcategory} {i + 1}", category=category, subcategory=subcategory,
            brand=f"Brand {i % 14 + 1}", supplier_id=f"S{i % 9:03}", unit_cost=money(cost),
            selling_price=money(price), current_stock=rng.choices([0, rng.randrange(1, 160)], [8, 92])[0],
            product_status="active",
        ))
    products = list(prices)
    popular = products[: max(1, len(products) // 5)]

    def product_choice():
        return activity.choice(popular if activity.random() < 0.6 else products)

    for i in range(sizing["orders"]):
        customer = activity.choice(data["customers"])
        _, _, region, currency = next(geo for geo in GEOGRAPHIES if geo[0] == customer["country"])
        status = activity.choices(["completed", "returned", "cancelled"], [88, 7, 5])[0]
        order_id = f"O{batch:05}-{i:07}"
        placed, method = event_time(), activity.choice(METHODS)
        data["orders"].append(dict(
            order_id=order_id, customer_id=customer["customer_id"], order_timestamp=placed,
            order_status=status, currency=currency, payment_method=method, shipping_region=region,
        ))
        if "order_items" in sizing:
            base, extra = divmod(sizing["order_items"], sizing["orders"])
            lines = base + int(i < extra)
        else:
            lines = activity.choices([1, 2, 3, 4], [46, 33, 16, 5])[0]
        total = 0
        for j in range(lines):
            product = product_choice()
            quantity = activity.choices([1, 2, 3, 4], [60, 24, 12, 4])[0]
            gross = prices[product] * quantity
            discount = gross * activity.choices([0, 5, 10, 20], [67, 10, 15, 8])[0] // 100
            tax = (gross - discount) * 7 // 100
            total += gross - discount + tax
            data["order_items"].append(dict(
                order_item_id=f"{order_id}-{j}", order_id=order_id, product_id=product, quantity=quantity,
                unit_price=money(prices[product]), discount=money(discount), tax=money(tax),
                line_total=money(gross - discount + tax),
            ))
        if "payments" in sizing:
            base, extra = divmod(sizing["payments"], sizing["orders"])
            attempts = base + int(i < extra)
        else:
            attempts = 1
        for j in range(attempts):
            payment_status = {"completed": "captured", "returned": "refunded", "cancelled": "failed"}[status]
            if j < attempts - 1:
                payment_status = "failed"
            data["payments"].append(dict(
                payment_id=f"T{order_id}-{j}", order_id=order_id, payment_timestamp=placed,
                payment_status=payment_status, transaction_amount=money(total), payment_method=method,
            ))
    for i in range(sizing["inventory"]):
        kind = activity.choice(["receipt", "sale", "return", "adjustment"])
        change = activity.randrange(1, 30) * (-1 if kind == "sale" else 1)
        data["inventory"].append(dict(
            event_id=f"I{batch:05}-{i:07}", product_id=product_choice(), event_timestamp=event_time(),
            event_type=kind, quantity_change=change, warehouse_id=f"WH-{i % 4 + 1}",
        ))
    event_index = 0
    while event_index < sizing["clickstream"]:
        session_id = f"S{batch:05}-{event_index:07}"
        customer = activity.choice(data["customers"])
        product, stamp = product_choice(), event_time()
        device = activity.choice(["Desktop", "Mobile", "Tablet"])
        stages = ["view", "cart", "checkout", "purchase"]
        depth = activity.choices([1, 2, 3, 4], [52, 26, 13, 9])[0]
        for kind in stages[: min(depth, sizing["clickstream"] - event_index)]:
            data["clickstream"].append(dict(
                event_id=f"E{batch:05}-{event_index:07}", session_id=session_id,
                customer_id=customer["customer_id"], timestamp=stamp, event_type=kind,
                product_id=product, device_type=device, traffic_source=customer["acquisition_channel"],
            ))
            event_index += 1
    for i in range(sizing["customer_activity"]):
        data["customer_activity"].append(dict(
            event_id=f"A{batch:05}-{i:07}", customer_id=activity.choice(data["customers"])["customer_id"],
            timestamp=event_time(), activity_type=activity.choice(["login", "search", "wishlist", "return_request"]),
        ))
    return data


CHALLENGES = [
    ("missing_value", "customers", "city", None),
    ("duplicate_record", "customers", None, None),
    ("invalid_timestamp", "orders", "order_timestamp", "invalid-date"),
    ("negative_quantity", "order_items", "quantity", -1),
    ("invalid_foreign_key", "inventory", "product_id", "P-not-registered"),
    ("schema_drift", "products", "unexpected_field", "drift"),
    ("incorrect_total", "order_items", "line_total", "0.03"),
    ("late_arrival", "clickstream", "timestamp", "2023-12-01T00:00:00+00:00"),
    ("statistical_anomaly", "payments", "transaction_amount", "99999999.99"),
]


def challenge(data):
    rows = {name: [dict(row) for row in values] for name, values in data.items()}
    labels = []
    occurrences = {}
    for defect, dataset, field, value in CHALLENGES:
        index = occurrences.get(dataset, 0)
        occurrences[dataset] = index + 1
        record = rows[dataset][index]
        labels.append({"defect": defect, "dataset": dataset, "record_id": record[FEEDS[dataset].key]})
        if field:
            record[field] = value
        else:
            rows[dataset].append(dict(record))
    return rows, labels


def export(data, output: Path, batch=0, file_format="json"):
    for dataset, rows in data.items():
        folder = output / dataset
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / f"batch-{batch:05}.{file_format}"
        temporary = file.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            if file_format == "csv":
                columns = list(dict.fromkeys([*FEEDS[dataset].fields, *(key for row in rows for key in row)]))
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            else:
                json.dump(rows, stream, ensure_ascii=False, separators=(",", ":"))
        temporary.replace(file)
