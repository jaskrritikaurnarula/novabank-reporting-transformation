# Management Reporting Prototype

Selected period: **31 December 2025**

## A. Network Overview

| KPI | Network value |
|---|---:|
| Active Customers | 4,560 |
| New Customers | 12 |
| Deposit Volume | €66.483 million |
| Loan Portfolio | €98.521 million |
| Portfolio-weighted Default Rate | 2.3% |
| Transaction Count | 5,166 |
| Month-over-Month Loan Growth | -1.2% |

Amounts and rates above are displayed using the approved presentation rounding. Calculations in the database retain full precision. Network loan growth compares the total current network portfolio with the total previous-month portfolio.

## B. Branch Comparison

The reproducible long-form comparison in `management/branch_comparison.csv` covers Active Customers, Deposit Volume, Loan Portfolio, and Default Rate for all 20 branches. It includes:

- reported branch value;
- unweighted average branch value;
- previous-month value and percentage movement; and
- KPI value rank.

KPI value rank is not a performance judgment. A high Default Rate, for example, is not desirable. Average branch Default Rate is also not the consolidated network rate; the overview uses the portfolio-weighted result.

## C. Exception and Commentary View

`management/management_exceptions.csv` contains 33 management-warning issues affecting 32 eligible branch-period-KPI results. It shows the rule, branch, period, KPI, description, review status, and commentary. One warning is documented as `ACCEPTED_WARNING`; the remaining warning examples are `UNDER_REVIEW`.

Warnings are management review prompts, not data-quality failures. The separate DQ control identified six deliberately invalid pre-load fixtures and zero critical failures in accepted constrained tables.

## Approved Reporting Adjustment

`management/reporting_adjustments.csv` shows the controlled example for B001 Deposit Volume in November 2025: the calculated value of €3,638,002.90 is retained and the approved reported value is €3,650,502.90. The source-like tables are not changed.
