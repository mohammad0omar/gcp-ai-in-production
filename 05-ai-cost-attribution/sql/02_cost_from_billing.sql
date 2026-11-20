-- Cost per customer, feature and day, from the Cloud Billing detailed usage export.
-- Replace BILLING_EXPORT_PROJECT (where the export dataset lives), WORKLOAD_PROJECT (the project
-- that runs the service), BILLING_DATASET, BILLING_ACCOUNT_ID, SERVICE_ID and the SKU ids.
-- Get SERVICE_ID and the SKU ids from 00_discover_skus.sql.
-- Rows missing a label are kept and shown as 'unlabelled'.
-- This groups by usage day. It will not match the console Cost table exactly: that table groups
-- by invoice month and includes late usage. Reconcile with 05_reconcile.sql instead.
SELECT
  DATE(usage_start_time) AS usage_date,
  COALESCE(cust.value, 'unlabelled') AS customer_hash,
  COALESCE(feat.value, 'unlabelled') AS feature,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)) AS cost
FROM `BILLING_EXPORT_PROJECT.BILLING_DATASET.gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID`
LEFT JOIN UNNEST(labels) AS cust ON cust.key = 'customer'
LEFT JOIN UNNEST(labels) AS feat ON feat.key = 'feature'
WHERE project.id = 'WORKLOAD_PROJECT'
  AND service.id = 'SERVICE_ID'
  AND sku.id IN ('SKU_ID_1', 'SKU_ID_2')
GROUP BY usage_date, customer_hash, feature;
