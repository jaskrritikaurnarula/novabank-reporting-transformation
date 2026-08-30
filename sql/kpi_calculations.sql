-- Rebuild the seven approved monthly branch KPIs deterministically.
-- Source-like tables are never modified by this script.

PRAGMA foreign_keys = ON;

BEGIN;

-- Adjustments reference KPI rows and must be removed before a full recalculation.
DELETE FROM reporting_adjustments;
DELETE FROM monthly_branch_kpis;

WITH
branch_periods AS (
    SELECT b.branch_id, r.reporting_period
    FROM branches b
    CROSS JOIN reporting_cycle_status r
),
eligible_open_accounts AS (
    SELECT
        a.account_id,
        a.customer_id,
        a.reporting_period,
        a.month_end_balance,
        cpa.home_branch_id
    FROM accounts a
    JOIN customer_period_assignments cpa
      ON cpa.customer_id = a.customer_id
     AND cpa.reporting_period = a.reporting_period
    WHERE a.product_category IN ('CURRENT', 'SAVINGS')
      AND date(a.open_date) <= date(a.reporting_period)
      AND (a.close_date IS NULL OR date(a.close_date) > date(a.reporting_period))
),
active_customers AS (
    SELECT
        home_branch_id AS branch_id,
        reporting_period,
        COUNT(DISTINCT customer_id) AS kpi_value
    FROM eligible_open_accounts
    GROUP BY home_branch_id, reporting_period
),
first_eligible_account AS (
    SELECT customer_id, MIN(date(open_date)) AS first_open_date
    FROM accounts
    WHERE product_category IN ('CURRENT', 'SAVINGS')
    GROUP BY customer_id
),
new_customers AS (
    SELECT
        cpa.home_branch_id AS branch_id,
        cpa.reporting_period,
        COUNT(*) AS kpi_value
    FROM first_eligible_account f
    JOIN customer_period_assignments cpa
      ON cpa.customer_id = f.customer_id
     AND cpa.reporting_period = date(f.first_open_date, 'start of month', '+1 month', '-1 day')
    GROUP BY cpa.home_branch_id, cpa.reporting_period
),
deposit_volume AS (
    SELECT
        home_branch_id AS branch_id,
        reporting_period,
        SUM(CASE WHEN month_end_balance > 0 THEN month_end_balance ELSE 0 END) AS kpi_value
    FROM eligible_open_accounts
    GROUP BY home_branch_id, reporting_period
),
eligible_open_loans AS (
    SELECT
        l.loan_id,
        l.reporting_period,
        l.outstanding_principal,
        l.loan_status,
        cpa.home_branch_id
    FROM loans l
    JOIN customer_period_assignments cpa
      ON cpa.customer_id = l.customer_id
     AND cpa.reporting_period = l.reporting_period
    WHERE l.loan_category IN ('PERSONAL_LOAN', 'AUTO_LOAN', 'MORTGAGE')
      AND date(l.open_date) <= date(l.reporting_period)
      AND (l.close_date IS NULL OR date(l.close_date) > date(l.reporting_period))
),
loan_metrics AS (
    SELECT
        home_branch_id AS branch_id,
        reporting_period,
        SUM(outstanding_principal) AS loan_portfolio,
        SUM(CASE WHEN loan_status = 'DEFAULT' THEN outstanding_principal ELSE 0 END) AS default_balance
    FROM eligible_open_loans
    GROUP BY home_branch_id, reporting_period
),
eligible_transactions AS (
    SELECT
        cpa.home_branch_id AS branch_id,
        t.reporting_period,
        COUNT(*) AS kpi_value
    FROM transactions t
    JOIN accounts a
      ON a.account_id = t.account_id
     AND a.reporting_period = t.reporting_period
    JOIN customer_period_assignments cpa
      ON cpa.customer_id = a.customer_id
     AND cpa.reporting_period = t.reporting_period
    WHERE t.transaction_status = 'POSTED'
      AND t.transaction_type IN (
          'CARD_PAYMENT', 'CASH_WITHDRAWAL', 'CASH_DEPOSIT',
          'TRANSFER_IN', 'TRANSFER_OUT', 'DIRECT_DEBIT'
      )
      AND date(t.posting_date) >= date(t.reporting_period, 'start of month')
      AND date(t.posting_date) <= date(t.reporting_period)
    GROUP BY cpa.home_branch_id, t.reporting_period
),
six_kpis AS (
    SELECT bp.branch_id, bp.reporting_period, 'ACTIVE_CUSTOMERS' AS kpi_id,
           CAST(COALESCE(ac.kpi_value, 0) AS REAL) AS calculated_value
    FROM branch_periods bp
    LEFT JOIN active_customers ac USING (branch_id, reporting_period)

    UNION ALL
    SELECT bp.branch_id, bp.reporting_period, 'NEW_CUSTOMERS',
           CAST(COALESCE(nc.kpi_value, 0) AS REAL)
    FROM branch_periods bp
    LEFT JOIN new_customers nc USING (branch_id, reporting_period)

    UNION ALL
    SELECT bp.branch_id, bp.reporting_period, 'DEPOSIT_VOLUME',
           COALESCE(dv.kpi_value, 0.0)
    FROM branch_periods bp
    LEFT JOIN deposit_volume dv USING (branch_id, reporting_period)

    UNION ALL
    SELECT bp.branch_id, bp.reporting_period, 'LOAN_PORTFOLIO',
           COALESCE(lm.loan_portfolio, 0.0)
    FROM branch_periods bp
    LEFT JOIN loan_metrics lm USING (branch_id, reporting_period)

    UNION ALL
    SELECT bp.branch_id, bp.reporting_period, 'DEFAULT_RATE',
           CASE
               WHEN COALESCE(lm.loan_portfolio, 0) = 0 THEN NULL
               ELSE lm.default_balance / lm.loan_portfolio * 100.0
           END
    FROM branch_periods bp
    LEFT JOIN loan_metrics lm USING (branch_id, reporting_period)

    UNION ALL
    SELECT bp.branch_id, bp.reporting_period, 'TRANSACTION_COUNT',
           CAST(COALESCE(et.kpi_value, 0) AS REAL)
    FROM branch_periods bp
    LEFT JOIN eligible_transactions et USING (branch_id, reporting_period)
)
INSERT INTO monthly_branch_kpis (
    branch_id, reporting_period, kpi_id,
    calculated_value, reported_value, calculated_at, result_status
)
SELECT
    branch_id,
    reporting_period,
    kpi_id,
    calculated_value,
    calculated_value,
    '2026-08-28T14:00:00',
    'PRELIMINARY'
FROM six_kpis;

-- KPI-07 is based on the already-calculated Loan Portfolio and uses LAG().
WITH loan_history AS (
    SELECT
        branch_id,
        reporting_period,
        calculated_value AS current_portfolio,
        LAG(calculated_value) OVER (
            PARTITION BY branch_id
            ORDER BY reporting_period
        ) AS previous_portfolio
    FROM monthly_branch_kpis
    WHERE kpi_id = 'LOAN_PORTFOLIO'
)
INSERT INTO monthly_branch_kpis (
    branch_id, reporting_period, kpi_id,
    calculated_value, reported_value, calculated_at, result_status
)
SELECT
    branch_id,
    reporting_period,
    'MOM_LOAN_GROWTH',
    CASE
        WHEN previous_portfolio IS NULL OR previous_portfolio = 0 THEN NULL
        ELSE (current_portfolio - previous_portfolio) / previous_portfolio * 100.0
    END,
    CASE
        WHEN previous_portfolio IS NULL OR previous_portfolio = 0 THEN NULL
        ELSE (current_portfolio - previous_portfolio) / previous_portfolio * 100.0
    END,
    '2026-08-28T14:00:00',
    'PRELIMINARY'
FROM loan_history;

COMMIT;
