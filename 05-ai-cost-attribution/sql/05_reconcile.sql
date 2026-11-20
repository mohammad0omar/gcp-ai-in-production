-- Reconcile: spend our SKU filter keeps vs ALL spend of the same service in the project,
-- for the last 30 usage days. Cost is cost plus credits, the same as 02_cost_from_billing.sql.
-- Replace the placeholders as in 02. A non-zero cost_missing_from_filter means a SKU is
-- missing from the list in 02. Spend without labels does not cause a difference
-- (02 keeps it as 'unlabelled').
WITH spend AS (
  SELECT
    sku.id AS sku_id,
    cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0) AS net_cost
  FROM `BILLING_EXPORT_PROJECT.BILLING_DATASET.gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID`
  WHERE project.id = 'WORKLOAD_PROJECT'
    AND service.id = 'SERVICE_ID'
    AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
)
SELECT
  SUM(IF(sku_id IN ('SKU_ID_1', 'SKU_ID_2'), net_cost, 0)) AS cost_in_filter,
  SUM(net_cost) AS cost_all_skus_of_service,
  SUM(IF(sku_id NOT IN ('SKU_ID_1', 'SKU_ID_2'), net_cost, 0)) AS cost_missing_from_filter
FROM spend;
