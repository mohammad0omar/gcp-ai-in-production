-- Run once after the first labelled calls are billed. Rows with our labels show which
-- service and SKU ids carry the Gemini cost. Copy them into 02_cost_from_billing.sql.
-- Only rows of the tutorial project are scanned.
-- Replace WORKLOAD_PROJECT, BILLING_EXPORT_PROJECT, BILLING_DATASET and BILLING_ACCOUNT_ID.
SELECT DISTINCT
  service.id AS service_id,
  service.description AS service_description,
  sku.id AS sku_id,
  sku.description AS sku_description
FROM `BILLING_EXPORT_PROJECT.BILLING_DATASET.gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID`
JOIN UNNEST(labels) AS feat ON feat.key = 'feature'
WHERE project.id = 'WORKLOAD_PROJECT'
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY service_id, sku_id;
