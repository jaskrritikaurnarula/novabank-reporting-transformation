"""Execute and test the SQL-led NovaBank Checkpoint 5 implementation."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "processed" / "novabank_reporting.db"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"
GENERATOR_PATH = PROJECT_ROOT / "src" / "generate_synthetic_data.py"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fetch_dicts(connection: sqlite3.Connection, query: str) -> list[dict]:
    cursor = connection.execute(query)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def execute_sql_pipeline(connection: sqlite3.Connection) -> None:
    connection.executescript((SQL_DIR / "kpi_calculations.sql").read_text(encoding="utf-8"))
    connection.executescript((SQL_DIR / "validation.sql").read_text(encoding="utf-8"))
    connection.executescript((SQL_DIR / "reporting_adjustment_demo.sql").read_text(encoding="utf-8"))


def pipeline_fingerprint(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for table, order_by in [
        ("monthly_branch_kpis", "branch_id, reporting_period, kpi_id"),
        ("validation_issues", "issue_id"),
        ("reporting_adjustments", "adjustment_id"),
        ("reporting_cycle_status", "reporting_period"),
    ]:
        cursor = connection.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
        digest.update(table.encode())
        for row in cursor.fetchall():
            digest.update(json.dumps(list(row), separators=(",", ":")).encode())
    return digest.hexdigest()


def parse_management_queries() -> dict[str, str]:
    text = (SQL_DIR / "management_queries.sql").read_text(encoding="utf-8")
    matches = list(re.finditer(r"^-- QUERY: ([a-z_]+)\s*$", text, flags=re.MULTILINE))
    queries = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[start:end].strip()
        comment_lines = []
        sql_lines = []
        for line in section.splitlines():
            if line.strip().startswith("--") and not sql_lines:
                comment_lines.append(line)
            else:
                sql_lines.append(line)
        queries[match.group(1)] = "\n".join(sql_lines).strip().rstrip(";")
    return queries


def kpi_sanity(connection: sqlite3.Connection) -> list[dict]:
    rows = []
    kpis = [row[0] for row in connection.execute("SELECT DISTINCT kpi_id FROM monthly_branch_kpis ORDER BY kpi_id")]
    for kpi_id in kpis:
        values = [
            row[0] for row in connection.execute(
                "SELECT calculated_value FROM monthly_branch_kpis WHERE kpi_id = ? AND calculated_value IS NOT NULL ORDER BY calculated_value",
                (kpi_id,),
            )
        ]
        nulls = connection.execute(
            "SELECT COUNT(*) FROM monthly_branch_kpis WHERE kpi_id = ? AND calculated_value IS NULL",
            (kpi_id,),
        ).fetchone()[0]
        rows.append({
            "kpi_id": kpi_id,
            "minimum": min(values) if values else None,
            "mean": statistics.fmean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "maximum": max(values) if values else None,
            "null_count": nulls,
        })
    return rows


def manual_example_checks(connection: sqlite3.Connection) -> dict:
    branch = "B001"
    period = "2024-01-31"
    direct_queries = {
        "ACTIVE_CUSTOMERS": """
            SELECT COUNT(DISTINCT a.customer_id)
            FROM accounts a
            JOIN customer_period_assignments cpa
              ON cpa.customer_id = a.customer_id AND cpa.reporting_period = a.reporting_period
            WHERE cpa.home_branch_id = ? AND a.reporting_period = ?
              AND a.product_category IN ('CURRENT', 'SAVINGS')
              AND date(a.open_date) <= date(a.reporting_period)
              AND (a.close_date IS NULL OR date(a.close_date) > date(a.reporting_period))
        """,
        "NEW_CUSTOMERS": """
            WITH first_account AS (
                SELECT customer_id, MIN(date(open_date)) first_open
                FROM accounts WHERE product_category IN ('CURRENT', 'SAVINGS') GROUP BY customer_id
            )
            SELECT COUNT(*)
            FROM first_account f
            JOIN customer_period_assignments cpa
              ON cpa.customer_id = f.customer_id
             AND cpa.reporting_period = date(f.first_open, 'start of month', '+1 month', '-1 day')
            WHERE cpa.home_branch_id = ? AND cpa.reporting_period = ?
        """,
        "DEPOSIT_VOLUME": """
            SELECT COALESCE(SUM(CASE WHEN a.month_end_balance > 0 THEN a.month_end_balance ELSE 0 END), 0)
            FROM accounts a JOIN customer_period_assignments cpa
              ON cpa.customer_id = a.customer_id AND cpa.reporting_period = a.reporting_period
            WHERE cpa.home_branch_id = ? AND a.reporting_period = ?
              AND a.product_category IN ('CURRENT', 'SAVINGS')
              AND date(a.open_date) <= date(a.reporting_period)
              AND (a.close_date IS NULL OR date(a.close_date) > date(a.reporting_period))
        """,
        "LOAN_PORTFOLIO": """
            SELECT COALESCE(SUM(l.outstanding_principal), 0)
            FROM loans l JOIN customer_period_assignments cpa
              ON cpa.customer_id = l.customer_id AND cpa.reporting_period = l.reporting_period
            WHERE cpa.home_branch_id = ? AND l.reporting_period = ?
              AND date(l.open_date) <= date(l.reporting_period)
              AND (l.close_date IS NULL OR date(l.close_date) > date(l.reporting_period))
        """,
        "DEFAULT_RATE": """
            SELECT CASE WHEN SUM(l.outstanding_principal) = 0 THEN NULL
                   ELSE SUM(CASE WHEN l.loan_status='DEFAULT' THEN l.outstanding_principal ELSE 0 END)
                        / SUM(l.outstanding_principal) * 100.0 END
            FROM loans l JOIN customer_period_assignments cpa
              ON cpa.customer_id = l.customer_id AND cpa.reporting_period = l.reporting_period
            WHERE cpa.home_branch_id = ? AND l.reporting_period = ?
              AND date(l.open_date) <= date(l.reporting_period)
              AND (l.close_date IS NULL OR date(l.close_date) > date(l.reporting_period))
        """,
        "TRANSACTION_COUNT": """
            SELECT COUNT(*) FROM transactions t
            JOIN accounts a ON a.account_id=t.account_id AND a.reporting_period=t.reporting_period
            JOIN customer_period_assignments cpa
              ON cpa.customer_id=a.customer_id AND cpa.reporting_period=t.reporting_period
            WHERE cpa.home_branch_id=? AND t.reporting_period=? AND t.transaction_status='POSTED'
              AND t.transaction_type IN ('CARD_PAYMENT','CASH_WITHDRAWAL','CASH_DEPOSIT','TRANSFER_IN','TRANSFER_OUT','DIRECT_DEBIT')
              AND date(t.posting_date) BETWEEN date(t.reporting_period,'start of month') AND date(t.reporting_period)
        """,
    }
    results = {}
    for kpi_id, query in direct_queries.items():
        expected = connection.execute(query, (branch, period)).fetchone()[0]
        actual = connection.execute(
            "SELECT calculated_value FROM monthly_branch_kpis WHERE branch_id=? AND reporting_period=? AND kpi_id=?",
            (branch, period, kpi_id),
        ).fetchone()[0]
        matches = expected is None and actual is None or expected is not None and actual is not None and abs(expected - actual) < 1e-8
        results[kpi_id] = {"direct_value": expected, "stored_value": actual, "matches": matches}
    growth = connection.execute(
        "SELECT calculated_value FROM monthly_branch_kpis WHERE branch_id=? AND reporting_period=? AND kpi_id='MOM_LOAN_GROWTH'",
        (branch, period),
    ).fetchone()[0]
    results["MOM_LOAN_GROWTH"] = {"direct_value": None, "stored_value": growth, "matches": growth is None}
    return results


def run_tests(connection: sqlite3.Connection, first_fingerprint: str, second_fingerprint: str) -> list[dict]:
    tests = []

    def add(test_id: str, description: str, passed: bool, evidence) -> None:
        tests.append({"test_id": test_id, "description": description, "passed": bool(passed), "evidence": evidence})

    row_count = connection.execute("SELECT COUNT(*) FROM monthly_branch_kpis").fetchone()[0]
    add("TC-02A", "20 branches × 24 periods × 7 KPIs", row_count == 3360, row_count)

    invalid_groups = connection.execute(
        "SELECT COUNT(*) FROM (SELECT branch_id, reporting_period, COUNT(*) n, COUNT(DISTINCT kpi_id) k FROM monthly_branch_kpis GROUP BY branch_id, reporting_period HAVING n<>7 OR k<>7)"
    ).fetchone()[0]
    duplicate_keys = connection.execute(
        "SELECT COUNT(*) FROM (SELECT branch_id, reporting_period, kpi_id, COUNT(*) n FROM monthly_branch_kpis GROUP BY 1,2,3 HAVING n>1)"
    ).fetchone()[0]
    add("TC-04", "Exactly one row per branch-period-KPI", invalid_groups == 0 and duplicate_keys == 0, {"invalid_groups": invalid_groups, "duplicate_keys": duplicate_keys})

    january_growth_nulls = connection.execute(
        "SELECT COUNT(*) FROM monthly_branch_kpis WHERE kpi_id='MOM_LOAN_GROWTH' AND reporting_period='2024-01-31' AND calculated_value IS NULL"
    ).fetchone()[0]
    ratio_mismatches = connection.execute("""
        SELECT COUNT(*) FROM monthly_branch_kpis d
        JOIN monthly_branch_kpis l USING (branch_id, reporting_period)
        WHERE d.kpi_id='DEFAULT_RATE' AND l.kpi_id='LOAN_PORTFOLIO'
          AND ((l.calculated_value=0 AND d.calculated_value IS NOT NULL)
            OR (l.calculated_value<>0 AND d.calculated_value IS NULL))
    """).fetchone()[0]
    add("TC-03", "Approved NULL handling", january_growth_nulls == 20 and ratio_mismatches == 0, {"first_month_growth_nulls": january_growth_nulls, "ratio_mismatches": ratio_mismatches})

    manual = manual_example_checks(connection)
    add("TC-02B", "Independent B001 January 2024 KPI checks", all(item["matches"] for item in manual.values()), manual)

    required_warning_codes = {
        "WARN_DEPOSIT_VOLUME_MOM_20", "WARN_LOAN_PORTFOLIO_MOM_20",
        "WARN_TRANSACTION_COUNT_MOM_20", "WARN_NEW_CUSTOMERS_MOM_20",
        "WARN_ACTIVE_CUSTOMERS_MOM_10", "WARN_DEFAULT_RATE_8",
        "WARN_ZERO_TRANSACTION_COUNT",
    }
    actual_warning_codes = {row[0] for row in connection.execute("SELECT DISTINCT rule_code FROM validation_issues WHERE severity='WARNING'")}
    add("TC-06A", "All approved warning rules fire from KPI values", required_warning_codes <= actual_warning_codes, sorted(actual_warning_codes))

    sql_critical = connection.execute("SELECT COUNT(*) FROM validation_issues WHERE issue_id LIKE 'SQL-C-%'").fetchone()[0]
    add("TC-05A", "Accepted-data SQL critical checks find no issues", sql_critical == 0, sql_critical)

    fixture_count = connection.execute("SELECT COUNT(*) FROM validation_issues WHERE issue_id LIKE 'INJ-C%' AND severity='CRITICAL'").fetchone()[0]
    october_blocked = connection.execute("SELECT publication_blocked FROM reporting_cycle_status WHERE reporting_period='2025-10-31'").fetchone()[0]
    add("TC-05B", "Six pre-load fixtures remain and October is blocked", fixture_count == 6 and october_blocked == 1, {"fixtures": fixture_count, "october_blocked": october_blocked})

    dq_failed = connection.execute("SELECT SUM(records_failed) FROM dq_source_rates").fetchone()[0]
    management_warnings = connection.execute("SELECT warning_issue_count FROM management_warning_summary").fetchone()[0]
    add("TC-06B", "Management warnings are not data-quality failures", dq_failed == 6 and management_warnings > 0, {"data_quality_failed_records": dq_failed, "management_warning_issues": management_warnings})

    under_review_periods = connection.execute("""
        SELECT COUNT(*) FROM publication_readiness
        WHERE publication_blocked=0 AND warnings_awaiting_disposition>0 AND publication_ready=0
    """).fetchone()[0]
    add("TC-06C", "UNDER_REVIEW warnings keep publication review incomplete", under_review_periods > 0, under_review_periods)

    reviewed_ready_periods = connection.execute("""
        SELECT COUNT(*)
        FROM publication_readiness p
        WHERE p.publication_ready=1
          AND EXISTS (
              SELECT 1 FROM validation_issues v
              WHERE v.reporting_period=p.reporting_period
                AND v.severity='WARNING'
                AND v.issue_status='ACCEPTED_WARNING'
                AND v.resolution_note IS NOT NULL
          )
          AND p.warnings_awaiting_disposition=0
    """).fetchone()[0]
    add("TC-06D", "Reviewed and explained warnings permit publication readiness", reviewed_ready_periods > 0, reviewed_ready_periods)

    october_readiness = fetch_dicts(connection, "SELECT * FROM publication_readiness WHERE reporting_period='2025-10-31'")
    october_ok = len(october_readiness) == 1 and october_readiness[0]["publication_blocked"] == 1 and october_readiness[0]["unresolved_critical_count"] == 6 and october_readiness[0]["publication_ready"] == 0
    add("TC-06E", "Unresolved critical issues block October regardless of warnings", october_ok, october_readiness)

    adjustment = fetch_dicts(connection, """
        SELECT a.adjustment_id, a.original_value, a.adjusted_value, a.status,
               k.calculated_value, k.reported_value
        FROM reporting_adjustments a
        JOIN monthly_branch_kpis k USING (branch_id, reporting_period, kpi_id)
    """)
    adjustment_ok = len(adjustment) == 1 and adjustment[0]["status"] == "APPROVED" and adjustment[0]["calculated_value"] == adjustment[0]["original_value"] and adjustment[0]["reported_value"] == adjustment[0]["adjusted_value"]
    add("TC-08", "Approved adjustment preserves calculated and reported values", adjustment_ok, adjustment)

    add("TC-11", "Repeated SQL execution is deterministic", first_fingerprint == second_fingerprint, {"first": first_fingerprint, "second": second_fingerprint})
    return tests


def main() -> None:
    # Start from the approved deterministic Checkpoint 4 source data.
    subprocess.run([sys.executable, str(GENERATOR_PATH), "--verify-repeatability"], cwd=PROJECT_ROOT, check=True, stdout=subprocess.DEVNULL)

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        execute_sql_pipeline(connection)
        source_rates_first = fetch_dicts(connection, "SELECT * FROM dq_source_rates ORDER BY source_table")
        period_rates_first = fetch_dicts(connection, "SELECT * FROM dq_period_rates ORDER BY reporting_period")
        management_warning_first = fetch_dicts(connection, "SELECT * FROM management_warning_summary")
        readiness_first = fetch_dicts(connection, "SELECT * FROM publication_readiness ORDER BY reporting_period")
        first_fingerprint = pipeline_fingerprint(connection)

        # A second full execution must produce the same database state.
        execute_sql_pipeline(connection)
        second_fingerprint = pipeline_fingerprint(connection)
        source_rates = fetch_dicts(connection, "SELECT * FROM dq_source_rates ORDER BY source_table")
        period_rates = fetch_dicts(connection, "SELECT * FROM dq_period_rates ORDER BY reporting_period")
        management_warning_summary = fetch_dicts(connection, "SELECT * FROM management_warning_summary")
        publication_readiness = fetch_dicts(connection, "SELECT * FROM publication_readiness ORDER BY reporting_period")
        if source_rates != source_rates_first or period_rates != period_rates_first or management_warning_summary != management_warning_first or publication_readiness != readiness_first:
            raise AssertionError("Quality or readiness output changed on rerun")

        sanity = kpi_sanity(connection)
        warning_counts = fetch_dicts(connection, """
            SELECT rule_code, COUNT(*) AS warning_count
            FROM validation_issues WHERE severity='WARNING'
            GROUP BY rule_code ORDER BY rule_code
        """)
        critical_counts = fetch_dicts(connection, """
            SELECT CASE WHEN issue_id LIKE 'INJ-C%' THEN 'PRE_LOAD_FIXTURE' ELSE 'ACCEPTED_SQL' END AS issue_source,
                   COUNT(*) AS critical_count
            FROM validation_issues WHERE severity='CRITICAL'
            GROUP BY issue_source ORDER BY issue_source
        """)
        tests = run_tests(connection, first_fingerprint, second_fingerprint)

        management_examples = {}
        for name, query in parse_management_queries().items():
            wrapped = f"SELECT * FROM ({query}) WHERE reporting_period='2025-12-31' LIMIT 10"
            management_examples[name] = fetch_dicts(connection, wrapped)

        adjustment = fetch_dicts(connection, """
            SELECT a.*, k.calculated_value, k.reported_value
            FROM reporting_adjustments a
            JOIN monthly_branch_kpis k USING (branch_id, reporting_period, kpi_id)
        """)
        overall = connection.execute("""
            SELECT SUM(records_failed), SUM(records_checked),
                   SUM(records_failed) * 100.0 / SUM(records_checked)
            FROM dq_source_rates
        """).fetchone()

        outputs = {
            "kpi_row_count": connection.execute("SELECT COUNT(*) FROM monthly_branch_kpis").fetchone()[0],
            "warning_counts": warning_counts,
            "critical_counts": critical_counts,
            "overall_exception_rate": {"records_failed": overall[0], "records_checked": overall[1], "exception_rate_pct": overall[2]},
            "management_warning_summary": management_warning_summary[0],
            "publication_ready_periods": sum(row["publication_ready"] for row in publication_readiness),
            "periods_awaiting_warning_disposition": sum(row["warnings_awaiting_disposition"] > 0 for row in publication_readiness),
            "adjustment": adjustment,
            "tests_passed": sum(item["passed"] for item in tests),
            "tests_total": len(tests),
            "pipeline_sha256": second_fingerprint,
        }
        if outputs["tests_passed"] != outputs["tests_total"]:
            raise AssertionError(f"Checkpoint 5 tests failed: {tests}")

        write_csv(PROCESSED_DIR / "kpi_sanity_summary.csv", sanity)
        write_csv(PROCESSED_DIR / "warning_counts.csv", warning_counts)
        write_csv(PROCESSED_DIR / "dq_source_exception_rates.csv", source_rates)
        write_csv(PROCESSED_DIR / "dq_period_exception_rates.csv", period_rates)
        write_csv(PROCESSED_DIR / "publication_readiness.csv", publication_readiness)
        write_csv(PROCESSED_DIR / "management_warning_summary.csv", management_warning_summary)
        (PROCESSED_DIR / "management_query_examples.json").write_text(json.dumps(management_examples, indent=2), encoding="utf-8")
        (PROCESSED_DIR / "checkpoint5_test_results.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
        (PROCESSED_DIR / "checkpoint5_summary.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
        print(json.dumps(outputs, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
