# Management Summary

## Situation

NovaBank is a fictional German retail bank whose monthly branch reporting depends on downloads, spreadsheet consolidation, manual checks, and repeated corrections. The case asks how that fragmented process could become timely, traceable, and comparable without introducing unnecessary system complexity.

## Reporting Results

For December 2025, the synthetic network reports 4,560 Active Customers, 12 New Customers, €66.483 million in Deposit Volume, €98.521 million in Loan Portfolio, 5,166 eligible posted transactions, and -1.2% network month-over-month loan growth. The consolidated portfolio-weighted Default Rate is 2.3%. These are illustrative synthetic results, not observations about a real bank.

## Key Exceptions

The implemented rules generate 33 management-warning issues across 32 of 2,800 assessed branch-period-KPI results, a 1.1429% Management Warning Rate. Default Rate above 8% is the most frequent rule with 11 warnings. Management warnings indicate results requiring review; they are not automatically data errors.

Data-quality validation is separate. Six deliberately invalid fixtures are detected before load and rejected from constrained tables. No critical issue is found in accepted data. The overall Data Quality Exception Rate is 6 of 448,575 checked records, or 0.0013%. October 2025 remains publication-blocked because the six synthetic critical fixtures are unresolved.

## Process Findings

The AS-IS analysis highlights manual consolidation, inconsistent KPI logic, repeated corrections, weak correction traceability, late issue discovery, analyst dependency, and reporting delay. These problems arise from the workflow design rather than from a need for advanced analytics.

## Proposed Reporting Model

The TO-BE model uses standardised T+1 extracts, a controlled load, T+2 automated validation, approved central KPI calculations, T+3 branch review, T+4 structured exception closure, and a T+5 management report. The timeline uses Monday–Friday working days; German public-holiday calendars are outside V1 scope. Original calculated values, approved adjustments, issue status, and publication state remain traceable.

## Recommendations

- Maintain controlled KPI definitions and test them when business rules change.
- Complete critical validation before branch review.
- Require a documented disposition for management warnings.
- Retain calculated, adjusted, and reported values separately.
- Monitor critical data-quality issues separately from unusual business results.
- Use average branch values for peer comparison and weighted rates for consolidated network ratios.

## Limitations

NovaBank and all records are fictional. Thresholds are fictional management rules rather than regulatory, statistical, or industry standards. Products, processes, and correction controls are simplified. The case does not implement regulatory reporting, a production workflow system, Power BI, or real customer data.
