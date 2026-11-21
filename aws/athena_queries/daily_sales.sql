-- Set the Glue database as the workgroup query context before running.
SELECT sale_date, revenue_usd
FROM daily_sales
ORDER BY sale_date DESC
LIMIT 90;
