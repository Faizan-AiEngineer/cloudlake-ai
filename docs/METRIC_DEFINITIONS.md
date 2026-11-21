# Metric definitions

| Metric | Definition |
| --- | --- |
| Recognized revenue / net sales | Completed line total less tax, converted to USD and rounded per line |
| Gross and discount amounts | Pre-discount line amount and separately recorded discount, converted per line |
| Refunds | Positive ex-tax line value for orders marked returned; presented separately from recognized revenue |
| Gross profit and margin | Recognized revenue less completed units times USD item cost; margin divides by recognized revenue |
| Completed orders / units | Distinct completed order IDs and sum of completed quantities in the filtered sales fact |
| Average order value | Recognized revenue divided by distinct completed orders |
| Active customers | Distinct buyers of completed orders in the filtered sales fact |
| Repeat rate | Share of those buyers with at least two distinct completed orders in the same filter |
| Return rate | Distinct returned order IDs divided by distinct orders with fact rows in the same filter |
| Conversion | Purchase-event sessions divided by view-event sessions; clickstream sessions are independently generated |
| Inventory turnover proxy | Units moved out on sale events divided by current stock; an operational proxy without average inventory history |
| Payment success | Captured and refunded attempts divided by all attempts |
| Growth | Current recognized sales divided by previous calendar month or prior-year calendar month, less one |
| Publication quality | Accepted rows divided by evaluated Bronze rows for the current published run |
| Source freshness | Elapsed time since the most recent committed ingestion; event watermarks describe a different clock |

Amounts exclude tax unless the field explicitly labels taxes or payment amounts. Cancelled orders recognize zero. Missing currencies are quarantined by foreign-key validation. Ratio denominators of zero yield null when no meaningful value exists.
