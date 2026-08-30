-- QUERY: current_vs_previous
-- All branch KPIs with prior-month comparison. NULL is retained when unavailable.
WITH history AS (
    SELECT
        branch_id,
        reporting_period,
        kpi_id,
        reported_value,
        LAG(reported_value) OVER (
            PARTITION BY branch_id, kpi_id
            ORDER BY reporting_period
        ) AS previous_month_value
    FROM monthly_branch_kpis
)
SELECT
    branch_id,
    reporting_period,
    kpi_id,
    reported_value AS current_value,
    previous_month_value,
    CASE
        WHEN previous_month_value IS NULL OR previous_month_value = 0 THEN NULL
        ELSE (reported_value - previous_month_value) / previous_month_value * 100.0
    END AS change_pct
FROM history
ORDER BY reporting_period, kpi_id, branch_id;

-- QUERY: branch_vs_network
-- Comparison with the unweighted average branch value. This is not always a
-- consolidated network KPI; in particular, average branch Default Rate is not
-- the same as the portfolio-weighted network Default Rate.
WITH comparison AS (
    SELECT
        branch_id,
        reporting_period,
        kpi_id,
        reported_value,
        AVG(reported_value) OVER (
            PARTITION BY reporting_period, kpi_id
        ) AS average_branch_value
    FROM monthly_branch_kpis
)
SELECT
    branch_id,
    reporting_period,
    kpi_id,
    reported_value AS branch_value,
    average_branch_value,
    reported_value - average_branch_value AS difference_from_average_branch
FROM comparison
ORDER BY reporting_period, kpi_id, branch_id;

-- QUERY: branch_ranking
-- Branch ranking by KPI value. Higher values receive rank 1; this is not a
-- performance ranking because a high value can be undesirable (e.g. Default Rate).
WITH ranked AS (
    SELECT
        branch_id,
        reporting_period,
        kpi_id,
        reported_value,
        RANK() OVER (
            PARTITION BY reporting_period, kpi_id
            ORDER BY reported_value DESC
        ) AS branch_rank
    FROM monthly_branch_kpis
    WHERE reported_value IS NOT NULL
)
SELECT branch_id, reporting_period, kpi_id, reported_value, branch_rank
FROM ranked
ORDER BY reporting_period, kpi_id, branch_rank, branch_id;

-- QUERY: weighted_network_default_rate
-- Proper consolidated network Default Rate, weighted by loan portfolio.
WITH branch_values AS (
    SELECT
        d.reporting_period,
        d.branch_id,
        d.reported_value AS default_rate,
        l.reported_value AS loan_portfolio
    FROM monthly_branch_kpis d
    JOIN monthly_branch_kpis l
      ON l.branch_id = d.branch_id
     AND l.reporting_period = d.reporting_period
     AND l.kpi_id = 'LOAN_PORTFOLIO'
    WHERE d.kpi_id = 'DEFAULT_RATE'
)
SELECT
    reporting_period,
    CASE
        WHEN SUM(loan_portfolio) = 0 THEN NULL
        ELSE SUM(default_rate / 100.0 * loan_portfolio) / SUM(loan_portfolio) * 100.0
    END AS portfolio_weighted_network_default_rate
FROM branch_values
GROUP BY reporting_period
ORDER BY reporting_period;
