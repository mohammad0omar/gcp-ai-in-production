-- The one view Data Studio reads. Joins customer names from a table you maintain.
-- customers(customer_hash STRING, customer_name STRING): fill it from your own app database.
-- It lives in its own dataset, ai_dashboard, which is the only dataset viewers can read.
CREATE OR REPLACE VIEW `WORKLOAD_PROJECT.ai_dashboard.dashboard` AS
SELECT
  v.usage_date,
  IFNULL(n.customer_name, v.customer_hash) AS customer,
  v.feature,
  IFNULL(v.calls, 0) AS calls,
  IFNULL(v.prompt_tokens, 0) + IFNULL(v.output_tokens, 0) + IFNULL(v.thoughts_tokens, 0)
    AS total_tokens,
  v.cost,
  v.cost_per_call
FROM `WORKLOAD_PROJECT.ai_cost.cost_per_customer_feature` AS v
LEFT JOIN `WORKLOAD_PROJECT.ai_cost.customers` AS n USING (customer_hash);
