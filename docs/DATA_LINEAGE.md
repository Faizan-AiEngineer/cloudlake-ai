# Data lineage

The [architecture](ARCHITECTURE.md) shows the processing graph. The API exposes declared relationships from registered feed names and fixed Gold SQL. Publication status is read separately from the metadata pointer.

- Orders depend on customers and rates. Lines depend on orders and products. Payments depend on orders. Inventory, clickstream and activity depend on their registered parents.
- `fact_sales` joins Silver orders, lines, products, customers and FX. Daily, monthly, product, customer, margin, region and channel metrics consume this fact.
- `fact_orders` feeds the returns and cancellations mart. `fact_payments` feeds payment success. Inventory and clickstream facts feed stock and conversion views.
- The Business Analytics route and executive reports use fixed queries over the published Gold fact and selected marts.

Bronze provenance joins a source object and record hash to the ingest run. A publication references an immutable run directory and committed manifests. A failed gate can be inspected via its run’s quarantine preview.
