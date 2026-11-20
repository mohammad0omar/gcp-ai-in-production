-- Tokens per customer, feature and day, from the log sink table.
-- Replace WORKLOAD_PROJECT with the project that runs the service and owns the sink dataset.
-- The log field `customer_id` holds the HASH; it is aliased to customer_hash here.
SELECT
  DATE(timestamp) AS usage_date,
  jsonPayload.customer_id AS customer_hash,
  jsonPayload.feature AS feature,
  COUNT(*) AS calls,
  SUM(jsonPayload.prompt_tokens) AS prompt_tokens,
  SUM(jsonPayload.output_tokens) AS output_tokens,
  SUM(jsonPayload.cached_tokens) AS cached_tokens,
  SUM(jsonPayload.thoughts_tokens) AS thoughts_tokens
FROM `WORKLOAD_PROJECT.ai_usage_logs.run_googleapis_com_stdout`
WHERE jsonPayload.event = 'ai_usage'
GROUP BY usage_date, customer_hash, feature;
