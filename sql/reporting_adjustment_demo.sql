-- One approved reporting-layer adjustment. Source-like tables remain unchanged.

PRAGMA foreign_keys = ON;

BEGIN;

DELETE FROM reporting_adjustments;

INSERT INTO reporting_adjustments (
    adjustment_id, branch_id, reporting_period, kpi_id,
    original_value, adjusted_value, reason, approver,
    approval_date, status, created_at
)
SELECT
    'ADJ-DEMO-001',
    branch_id,
    reporting_period,
    kpi_id,
    calculated_value,
    calculated_value + 12500.0,
    'Synthetic demonstration: understood deposit-source timing issue not correctable before T+5.',
    'Head of Retail Banking',
    '2025-12-04',
    'APPROVED',
    '2025-12-03T10:00:00'
FROM monthly_branch_kpis
WHERE branch_id = 'B001'
  AND reporting_period = '2025-11-30'
  AND kpi_id = 'DEPOSIT_VOLUME';

UPDATE monthly_branch_kpis
SET reported_value = (
    SELECT adjusted_value
    FROM reporting_adjustments a
    WHERE a.branch_id = monthly_branch_kpis.branch_id
      AND a.reporting_period = monthly_branch_kpis.reporting_period
      AND a.kpi_id = monthly_branch_kpis.kpi_id
      AND a.status = 'APPROVED'
)
WHERE branch_id = 'B001'
  AND reporting_period = '2025-11-30'
  AND kpi_id = 'DEPOSIT_VOLUME';

COMMIT;
