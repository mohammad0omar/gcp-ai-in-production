-- Join tokens and cost. Both inputs are the queries in 01 and 02 saved as views.
-- FULL OUTER JOIN keeps billing-only rows (a missing log) and log-only rows (billing not
-- arrived yet). Missing cost stays NULL, not 0. cost_per_call is a daily aggregate ratio
-- from two sources, so treat it as an average, not the price of one call.
CREATE OR REPLACE VIEW `WORKLOAD_PROJECT.ai_cost.cost_per_customer_feature` AS
SELECT
  COALESCE(t.usage_date, c.usage_date) AS usage_date,
  COALESCE(t.customer_hash, c.customer_hash) AS customer_hash,
  COALESCE(t.feature, c.feature) AS feature,
  t.calls,
  t.prompt_tokens,
  t.output_tokens,
  t.cached_tokens,
  t.thoughts_tokens,
  c.cost,
  SAFE_DIVIDE(c.cost, t.calls) AS cost_per_call
FROM `WORKLOAD_PROJECT.ai_cost.tokens_daily` AS t
FULL OUTER JOIN `WORKLOAD_PROJECT.ai_cost.cost_daily` AS c
  ON c.usage_date = t.usage_date
  AND c.customer_hash = t.customer_hash
  AND c.feature = t.feature;
