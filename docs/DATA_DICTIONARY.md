# Data dictionary

The [schema registry](../data_engineering/schema.py) is the executable source of field names, Spark types, primary keys, event timestamps and foreign keys. Currency amounts are decimals. Event timestamps normalize to UTC. Clean feeds use non-empty registered columns.

| Feed | Grain and key | Business fields |
| --- | --- | --- |
| Customers | One account per `customer_id` | Registration date, country, city, age group, segment, acquisition channel and account status |
| Products | One catalog product per `product_id` | Name, category, subcategory, brand, supplier, USD unit cost, list price, current stock and status |
| Orders | One order per `order_id` | Customer, order timestamp, status, currency, payment method and shipping region |
| Order items | One line per `order_item_id` | Order, product, positive quantity, local unit price, local discount and tax amounts, line total |
| Payments | One attempt per `payment_id` | Order, payment timestamp, method, status and local amount |
| Inventory | One movement per `event_id` | Product, timestamp, nonzero movement, event type and warehouse |
| Clickstream | One event per `event_id` | Session, customer, timestamp, funnel stage, product, device and traffic source |
| Customer activity | One event per `event_id` | Customer, timestamp and activity type |
| Rates | One quote per `currency` | USD per local unit and provenance. Default rates are illustrative and non-historical |

Bronze adds canonical source payload, ingestion timestamp, source name, source file, ingestion run ID, schema version, record SHA-256 and source record ordinal. Silver enforces declared types and registered fields. Its order and line records remain in source currency. Gold applies currency normalization to USD with dataset-wide rate lookup.

Quarantine retains original payload, source filename, record hash, dataset, run ID, business key, rejection reason and detection time. The challenge generator writes label records separately. Lateness is advisory and anomalies without violated domain rules remain valid.
