# Checkpoint 4 Data Dictionary

## Source-like tables

| Table | Grain | Primary key | Important foreign keys | Purpose |
|---|---|---|---|---|
| `branches` | One branch | `branch_id` | — | Twenty fictional reporting branches |
| `customers` | One customer | `customer_id` | — | Synthetic customer population |
| `customer_period_assignments` | One customer per month | `customer_id`, `reporting_period` | Customer and home branch | Direct statement of the customer's home branch for that month |
| `accounts` | One account snapshot per month | `account_id`, `reporting_period` | Customer | Product eligibility and month-end balance |
| `loans` | One loan snapshot per month | `loan_id`, `reporting_period` | Customer | Outstanding portfolio and monthly default status |
| `transactions` | One transaction | `transaction_id` | Account-period snapshot | Monthly account activity |

## Control and reporting tables

| Table | Grain | Primary key | Purpose |
|---|---|---|---|
| `validation_issues` | One detected rule failure | `issue_id` | Severity, ownership, review status, and resolution |
| `reporting_adjustments` | One branch-KPI-period adjustment | `adjustment_id` | Controlled reporting-layer adjustments |
| `reporting_cycle_status` | One reporting month | `reporting_period` | T+1 to T+5 stage status and publication blocking |
| `monthly_branch_kpis` | One branch, month, and KPI | `branch_id`, `reporting_period`, `kpi_id` | Future calculated and reported KPI values |

## Important field definitions

| Field | Definition |
|---|---|
| `reporting_period` | Calendar month-end from 2024-01-31 through 2025-12-31 |
| `home_branch_id` | The one branch assigned to a customer for that reporting period |
| `month_end_balance` | Full-precision synthetic account balance; negative CURRENT balances remain in source data |
| `outstanding_principal` | Non-negative synthetic loan balance at month-end |
| `loan_status` | `PERFORMING`, `DEFAULT`, or `CLOSED` |
| `calculated_value` | Future full-precision result derived from source-like tables |
| `reported_value` | Future final result after any approved reporting-layer adjustment |
| `publication_blocked` | 1 when unresolved critical issues prevent final publication; otherwise 0 |
| `publication_ready` | Derived cycle status: 1 only when no unresolved critical issue, warning awaiting disposition, or pending adjustment remains |
| Data Quality Exception Rate | Percentage of checked records with at least one CRITICAL validation failure; management warnings are excluded |
| Management Warning Rate | Percentage of eligible branch-period-KPI results with at least one management warning |
| `average_branch_value` | Unweighted arithmetic mean of branch KPI values for a period; not a consolidated weighted network rate |
| `portfolio_weighted_network_default_rate` | Consolidated Default Rate using branch Loan Portfolio as the weight |
| `branch_rank` | Rank by KPI value; it does not imply that rank 1 is best performance |

The complete field-level definitions, constraints, controlled values, and relationships are executable in `sql/schema.sql`.

Reporting-cycle stage dates advance Monday-Friday only. German public-holiday calendars are outside V1 scope.
