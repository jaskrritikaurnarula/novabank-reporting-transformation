# AS-IS and TO-BE Reporting Comparison

| Area | AS-IS | TO-BE | Business benefit |
|---|---|---|---|
| Data collection | Analysts download separate source files | Standardised extracts enter a controlled load | Reduces manual consolidation and makes inputs repeatable |
| Validation | Manual checks occur during spreadsheet work | Automated validation runs at T+2 before branch review | Finds critical issues earlier and applies the same checks each month |
| KPI definitions | Logic may differ between files or analysts | Approved definitions are implemented centrally in SQL | Makes branch results comparable and calculation logic inspectable |
| Issue classification | Data problems and unusual results are mixed together | Critical data failures and management warnings are classified separately | Prevents unusual-but-valid results from being treated automatically as errors |
| Correction handling | Corrections arrive through email or spreadsheets | Structured branch review and controlled KPI-level adjustments | Retains original values, approval, reason, and final reported value |
| Traceability | Rework is difficult to reconstruct | Validation issues, adjustments, cycle status, and tests retain evidence | Supports review of what changed, why, and by whom |
| Reporting timeline | Repeated rework can delay the report | T+1 extracts, T+2 validation, T+3 review, T+4 closure, T+5 reporting | Establishes clear working-day responsibilities and hand-offs |
| Data-quality ownership | Analysts coordinate issues informally | Issues carry severity, status, owner, and resolution information | Makes follow-up visible without expanding V1 into a workflow platform |
| Management output | A final spreadsheet/report is assembled manually | Network overview, branch comparison, and exception/commentary views | Gives management a consistent summary with supporting detail |

The case does not claim measured time or cost savings. Benefits describe the intended effect of the proposed design.
