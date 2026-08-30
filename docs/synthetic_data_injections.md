# Synthetic Data Injections

All records are fictional. The accepted source-like CSV files and SQLite tables satisfy the relational schema. Critical defects that would violate a primary key, required field, foreign key, or value constraint are stored in `data/synthetic_raw/injected_critical_records.csv` as pre-load validation fixtures. The generator parses each fixture, runs the relevant rule, and creates a `validation_issues` row only when the defect is detected.

## Critical fixtures

| Issue ID | Source table | Affected key | Issue type | Reason injected | Expected validation result |
|---|---|---|---|---|---|
| INJ-C01 | `customer_period_assignments` | `C00001\|2025-10-31` | Missing branch ID | Tests required historical branch attribution | Create CRITICAL issue, reject fixture record, block publication |
| INJ-C02 | `transactions` | `T_BAD_001` | Missing reporting period | Tests required monthly attribution | Create CRITICAL issue, reject fixture record, block publication |
| INJ-C03 | `customers` | `C00001` | Duplicate primary identifier | Tests duplicate detection before PK enforcement | Create CRITICAL issue, reject duplicate, block publication |
| INJ-C04 | `accounts` | `A_BAD_001\|2025-10-31` | Invalid customer relationship | Tests foreign-key-style validation | Create CRITICAL issue, reject fixture record, block publication |
| INJ-C05 | `loans` | `L_BAD_001\|2025-10-31` | Negative outstanding principal | Tests impossible loan balance | Create CRITICAL issue, reject fixture record, block publication |
| INJ-C06 | `monthly_branch_kpis` | `B001\|2025-10-31\|ACTIVE_CUSTOMERS` | Duplicate branch-period-KPI result | Tests uniqueness of derived reporting output | Create CRITICAL issue, reject duplicate result, block publication |

The six corresponding rows are loaded into `validation_issues` with severity `CRITICAL` and status `OPEN`. The October 2025 reporting cycle is marked as publication-blocked. The final constrained tables do not contain the invalid fixture records.

## Warning scenarios embedded in valid data

These scenarios remain valid source records. They are designed to create warnings during Checkpoint 5 validation; they must not be rejected or automatically corrected.

| Scenario | Affected branch and period | Confirmed synthetic result | Expected validation result |
|---|---|---:|---|
| Deposit Volume absolute MoM movement above 20% | B020, March 2025 | +42.0% | WARNING; retain value and request review |
| Loan Portfolio absolute MoM movement above 20% | B019, April 2025 | +159.1% | WARNING; retain value and request review |
| Transaction Count absolute MoM movement above 20% | B018, May 2025 | +30.4% | WARNING; retain value and request review |
| New Customers absolute MoM movement above 20% and absolute count change at least 5 | B017, June 2025 | +510.0% | WARNING; retain value and request review |
| Active Customers absolute MoM movement above 10% | B016, July 2025 | +22.5% | WARNING; retain value and request review |
| Default Rate above 8% | B015, August 2025 | 20.1% | WARNING; retain value and request review |
| Transaction Count equals zero | B014, September 2025 | 0 | WARNING; retain zero and request review |

The thresholds are fictional management rules for this portfolio case. They are not regulatory, statistical, or industry standards. Values above are verification calculations only; final KPI records and validation SQL are intentionally deferred to Checkpoint 5.
