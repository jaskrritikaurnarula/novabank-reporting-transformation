# Checkpoint 5 Business-Rule Clarifications

## Data quality and management warnings

The Data Quality Exception Rate measures records with CRITICAL validation failures. KPI movement and threshold warnings are management-review signals and are reported separately as a Management Warning Rate.

## New Customers warning

Create a warning only when both conditions are true:

- absolute month-over-month percentage change is greater than 20%; and
- absolute customer-count change is at least 5.

If the previous value is missing or zero, the percentage movement is NULL and this rule does not create an infinite percentage.

## Publication decisions

- `publication_blocked = 1` only when unresolved CRITICAL issues exist.
- `publication_ready = 1` requires no unresolved critical issue, no warning awaiting disposition, and no pending reporting adjustment.
- A warning with status `UNDER_REVIEW` requires disposition but does not itself set the critical blocking flag.
- A documented warning with status `ACCEPTED_WARNING` is treated as reviewed and does not prevent readiness.

No separate correction-request entity exists in V1. Pending branch-KPI-period reporting adjustments are the implemented correction-control check.

## Comparison and ranking language

The windowed `AVG()` result is labelled **average branch value**, because it gives every branch equal weight. For Default Rate, that value is not the same as a consolidated network rate. The consolidated network Default Rate is calculated separately by weighting each branch Default Rate by its Loan Portfolio.

Branch ordering is labelled **KPI value rank**, not performance ranking. Direction and desirability depend on the KPI.

All thresholds in this project are fictional business-management thresholds for the synthetic portfolio case. They are not regulatory, statistical, or industry-standard thresholds.
