"""Generate deterministic, entirely fictional NovaBank reporting data.

The accepted CSV files satisfy the relational schema. Deliberately invalid
critical records are written to a separate pre-load fixture because primary-
key and foreign-key failures cannot be loaded into constrained SQLite tables.
"""

from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import tempfile


SEED = 20250828
GENERATED_AT = "2026-08-28T12:00:00"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "synthetic_raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
DATABASE_PATH = PROCESSED_DIR / "novabank_reporting.db"

ACCOUNT_PRODUCTS = ["CURRENT", "SAVINGS", "TERM_DEPOSIT", "SECURITIES"]
LOAN_PRODUCTS = ["PERSONAL_LOAN", "AUTO_LOAN", "MORTGAGE"]
ELIGIBLE_TRANSACTION_TYPES = [
    "CARD_PAYMENT", "CASH_WITHDRAWAL", "CASH_DEPOSIT",
    "TRANSFER_IN", "TRANSFER_OUT", "DIRECT_DEBIT",
]
EXCLUDED_TRANSACTION_TYPES = [
    "REVERSAL", "FEE", "INTEREST", "LOAN_DISBURSEMENT", "LOAN_REPAYMENT",
]


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def reporting_periods() -> list[date]:
    periods = []
    year, month = 2024, 1
    for _ in range(24):
        periods.append(month_end(year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return periods


def period_for_day(value: date) -> date:
    return month_end(value.year, value.month)


def random_day(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def is_open(open_date: date, close_date: date | None, period: date) -> bool:
    return open_date <= period and (close_date is None or close_date > period)


def add_working_days(start: date, number_of_days: int) -> date:
    """Advance Monday-Friday only; public holidays are outside V1 scope."""
    current = start
    added = 0
    while added < number_of_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def weighted_choice(rng: random.Random, values: list[str], weights: list[int]) -> str:
    return rng.choices(values, weights=weights, k=1)[0]


def make_branches() -> list[dict]:
    cities = [
        ("Hamburg Alster", "Hamburg", "NORTH"), ("Kiel Zentrum", "Kiel", "NORTH"),
        ("Lübeck Altstadt", "Lübeck", "NORTH"), ("Bremen Mitte", "Bremen", "NORTH"),
        ("Hannover City", "Hannover", "NORTH"), ("München Zentrum", "München", "SOUTH"),
        ("Nürnberg Altstadt", "Nürnberg", "SOUTH"), ("Stuttgart Mitte", "Stuttgart", "SOUTH"),
        ("Augsburg Rathaus", "Augsburg", "SOUTH"), ("Freiburg Zentrum", "Freiburg", "SOUTH"),
        ("Berlin Alexanderplatz", "Berlin", "EAST"), ("Leipzig Zentrum", "Leipzig", "EAST"),
        ("Dresden Altmarkt", "Dresden", "EAST"), ("Potsdam Mitte", "Potsdam", "EAST"),
        ("Erfurt Zentrum", "Erfurt", "EAST"), ("Köln Dom", "Köln", "WEST"),
        ("Düsseldorf Mitte", "Düsseldorf", "WEST"), ("Dortmund Zentrum", "Dortmund", "WEST"),
        ("Essen City", "Essen", "WEST"), ("Frankfurt Hauptwache", "Frankfurt am Main", "WEST"),
    ]
    return [
        {
            "branch_id": f"B{index:03d}", "branch_name": f"NovaBank {name}",
            "city": city, "region": region, "open_date": "2005-01-01", "close_date": None,
        }
        for index, (name, city, region) in enumerate(cities, start=1)
    ]


def make_customers(rng: random.Random, periods: list[date]) -> tuple[list[dict], dict[str, date]]:
    customers = []
    created_dates = {}
    for number in range(1, 5001):
        customer_id = f"C{number:05d}"
        if number <= 4700:
            created = random_day(rng, date(2010, 1, 1), date(2023, 12, 15))
        elif number <= 4940:
            regular_index = number - 4701
            period = periods[regular_index // 10]
            created = date(period.year, period.month, rng.randint(1, 15))
        else:
            created = date(2025, 6, rng.randint(1, 15))
        created_dates[customer_id] = created
        customers.append({
            "customer_id": customer_id,
            "customer_created_date": created.isoformat(),
            "customer_status": "INACTIVE" if number % 47 == 0 else "ACTIVE",
        })
    return customers, created_dates


def make_assignments(
    rng: random.Random, periods: list[date], created_dates: dict[str, date]
) -> tuple[list[dict], dict[tuple[str, str], str]]:
    branch_ids = [f"B{number:03d}" for number in range(1, 21)]
    branch_weights = [9, 5, 4, 6, 8, 10, 6, 9, 4, 3, 10, 7, 7, 4, 4, 10, 9, 7, 6, 10]
    initial_branch = {}
    for number in range(1, 5001):
        customer_id = f"C{number:05d}"
        if 4861 <= number <= 4870 or number >= 4941:
            initial_branch[customer_id] = "B017"
        else:
            initial_branch[customer_id] = weighted_choice(rng, branch_ids, branch_weights)

    transfer_candidates = [customer_id for customer_id, branch in initial_branch.items() if branch == "B013" and int(customer_id[1:]) <= 4700]
    transfer_to_b016 = set(transfer_candidates[:80])
    normal_candidates = [f"C{number:05d}" for number in range(1, 4701) if f"C{number:05d}" not in transfer_to_b016]
    normal_transfers = sorted(rng.sample(normal_candidates, 70))
    normal_transfer_set = set(normal_transfers)
    transfer_period = {customer_id: rng.choice(periods[8:20]) for customer_id in normal_transfers}
    transfer_target = {
        customer_id: rng.choice([branch for branch in branch_ids if branch != initial_branch[customer_id]])
        for customer_id in normal_transfers
    }

    assignments = []
    lookup = {}
    for customer_id, created in created_dates.items():
        start_period = period_for_day(created)
        for period in periods:
            if period < start_period:
                continue
            branch = initial_branch[customer_id]
            if customer_id in transfer_to_b016 and period >= date(2025, 7, 31):
                branch = "B016"
            elif customer_id in normal_transfer_set and period >= transfer_period[customer_id]:
                branch = transfer_target[customer_id]
            lookup[(customer_id, period.isoformat())] = branch
            assignments.append({
                "customer_id": customer_id,
                "reporting_period": period.isoformat(),
                "home_branch_id": branch,
            })
    return assignments, lookup


def make_account_masters(
    rng: random.Random, periods: list[date], created_dates: dict[str, date]
) -> list[dict]:
    masters = []
    for number in range(1, 5001):
        customer_id = f"C{number:05d}"
        if number >= 4941:
            opened = date(2025, 6, rng.randint(1, 15))
            product = "CURRENT" if number % 2 else "SAVINGS"
        elif number >= 4701:
            created = created_dates[customer_id]
            opened = created + timedelta(days=rng.randint(0, 5))
            product = "CURRENT" if number % 3 else "SAVINGS"
        else:
            opened = random_day(rng, max(created_dates[customer_id], date(2012, 1, 1)), date(2023, 12, 20))
            product = weighted_choice(rng, ACCOUNT_PRODUCTS, [62, 25, 7, 6])
        masters.append({
            "account_id": f"A{number:06d}", "customer_id": customer_id,
            "product_category": product, "open_date": opened, "close_date": None,
        })

    for number in range(5001, 7001):
        customer_number = rng.randint(1, 4940)
        customer_id = f"C{customer_number:05d}"
        opened = random_day(rng, max(created_dates[customer_id], date(2015, 1, 1)), date(2025, 12, 20))
        close_date = None
        if rng.random() < 0.08 and opened < date(2025, 6, 1):
            close_period = rng.choice([period for period in periods if period > period_for_day(opened)])
            close_date = close_period if rng.random() < 0.5 else close_period.replace(day=max(1, close_period.day - 10))
        masters.append({
            "account_id": f"A{number:06d}", "customer_id": customer_id,
            "product_category": weighted_choice(rng, ACCOUNT_PRODUCTS, [56, 28, 9, 7]),
            "open_date": opened, "close_date": close_date,
        })
    return masters


def initial_account_balance(rng: random.Random, product: str) -> float:
    if product == "CURRENT":
        return rng.uniform(-800, 9000)
    if product == "SAVINGS":
        return rng.uniform(200, 35000)
    if product == "TERM_DEPOSIT":
        return rng.uniform(5000, 70000)
    return rng.uniform(2000, 90000)


def make_accounts(
    rng: random.Random, periods: list[date], masters: list[dict], assignment_lookup: dict
) -> list[dict]:
    rows = []
    for master in masters:
        balance = initial_account_balance(rng, master["product_category"])
        for period in periods:
            if period < period_for_day(master["open_date"]):
                continue
            if master["close_date"] is not None and period > period_for_day(master["close_date"]):
                continue
            if (master["customer_id"], period.isoformat()) not in assignment_lookup:
                continue
            movement = rng.gauss(120, 700 if master["product_category"] == "CURRENT" else 1300)
            balance += movement
            if master["product_category"] != "CURRENT":
                balance = max(0, balance)
            branch = assignment_lookup[(master["customer_id"], period.isoformat())]
            if branch == "B020" and period == date(2025, 3, 31) and master["product_category"] in {"CURRENT", "SAVINGS"} and balance > 0:
                balance *= 1.40
            rows.append({
                "account_id": master["account_id"], "reporting_period": period.isoformat(),
                "customer_id": master["customer_id"], "product_category": master["product_category"],
                "open_date": master["open_date"].isoformat(),
                "close_date": master["close_date"].isoformat() if master["close_date"] else None,
                "month_end_balance": round(balance, 2), "currency_code": "EUR",
            })
    return rows


def make_loan_masters(
    rng: random.Random, assignment_lookup: dict
) -> list[dict]:
    masters = []
    for number in range(1, 1431):
        customer_id = f"C{rng.randint(1, 4940):05d}"
        opened = random_day(rng, date(2015, 1, 1), date(2025, 8, 20))
        category = weighted_choice(rng, LOAN_PRODUCTS, [50, 27, 23])
        masters.append({
            "loan_id": f"L{number:06d}", "customer_id": customer_id,
            "loan_category": category, "open_date": opened, "close_date": None,
        })

    b019_customers = [
        customer_id for (customer_id, period), branch in assignment_lookup.items()
        if period == "2025-04-30" and branch == "B019"
    ]
    for number in range(1431, 1501):
        masters.append({
            "loan_id": f"L{number:06d}", "customer_id": rng.choice(b019_customers),
            "loan_category": weighted_choice(rng, LOAN_PRODUCTS, [55, 30, 15]),
            "open_date": date(2025, 4, rng.randint(1, 15)), "close_date": None,
        })
    return masters


def starting_loan_balance(rng: random.Random, category: str) -> float:
    if category == "PERSONAL_LOAN":
        return rng.uniform(3000, 30000)
    if category == "AUTO_LOAN":
        return rng.uniform(8000, 45000)
    return rng.uniform(90000, 450000)


def make_loans(
    rng: random.Random, periods: list[date], masters: list[dict], assignment_lookup: dict
) -> list[dict]:
    rows = []
    for master in masters:
        balance = starting_loan_balance(rng, master["loan_category"])
        monthly_payment = balance / rng.randint(36, 240)
        default_start = rng.choice(periods[5:]) if rng.random() < 0.035 else None
        for period in periods:
            if period < period_for_day(master["open_date"]):
                continue
            if (master["customer_id"], period.isoformat()) not in assignment_lookup:
                continue
            balance = max(0, balance - monthly_payment)
            status = "DEFAULT" if default_start and period >= default_start and rng.random() < 0.75 else "PERFORMING"
            rows.append({
                "loan_id": master["loan_id"], "reporting_period": period.isoformat(),
                "customer_id": master["customer_id"], "loan_category": master["loan_category"],
                "open_date": master["open_date"].isoformat(), "close_date": None,
                "outstanding_principal": round(balance, 2), "loan_status": status,
                "currency_code": "EUR",
            })

    august = "2025-08-31"
    b015_indices = [
        index for index, row in enumerate(rows)
        if row["reporting_period"] == august
        and assignment_lookup[(row["customer_id"], august)] == "B015"
        and row["outstanding_principal"] > 0
    ]
    total = sum(rows[index]["outstanding_principal"] for index in b015_indices)
    default_total = sum(rows[index]["outstanding_principal"] for index in b015_indices if rows[index]["loan_status"] == "DEFAULT")
    for index in sorted(b015_indices, key=lambda item: rows[item]["outstanding_principal"], reverse=True):
        if total and default_total / total > 0.09:
            break
        if rows[index]["loan_status"] != "DEFAULT":
            rows[index]["loan_status"] = "DEFAULT"
            default_total += rows[index]["outstanding_principal"]
    return rows


def transaction_amount(rng: random.Random, transaction_type: str) -> float:
    if transaction_type in {"CARD_PAYMENT", "CASH_WITHDRAWAL", "DIRECT_DEBIT", "TRANSFER_OUT", "FEE", "LOAN_REPAYMENT"}:
        return round(-abs(rng.gauss(90, 120)), 2)
    return round(abs(rng.gauss(250, 400)), 2)


def make_transactions(
    rng: random.Random, accounts: list[dict], assignment_lookup: dict
) -> list[dict]:
    rows = []
    eligible_counts = {}
    account_by_branch_period = {}
    transaction_number = 1
    for account in accounts:
        period = date.fromisoformat(account["reporting_period"])
        open_date = date.fromisoformat(account["open_date"])
        close_date = date.fromisoformat(account["close_date"]) if account["close_date"] else None
        if not is_open(open_date, close_date, period):
            continue
        branch = assignment_lookup[(account["customer_id"], account["reporting_period"])]
        account_by_branch_period.setdefault((branch, account["reporting_period"]), []).append(account)
        draws = 1 if rng.random() < 0.70 else 0
        if rng.random() < 0.18:
            draws += 1
        for _ in range(draws):
            transaction_type = weighted_choice(
                rng, ELIGIBLE_TRANSACTION_TYPES + EXCLUDED_TRANSACTION_TYPES,
                [28, 10, 5, 16, 16, 15, 2, 3, 2, 1, 2],
            )
            status = weighted_choice(rng, ["POSTED", "PENDING", "DECLINED"], [94, 3, 3])
            if branch == "B014" and account["reporting_period"] == "2025-09-30":
                if transaction_type in ELIGIBLE_TRANSACTION_TYPES and status == "POSTED":
                    transaction_type = "FEE"
            posting_day = rng.randint(1, period.day)
            row = {
                "transaction_id": f"T{transaction_number:09d}",
                "account_id": account["account_id"], "reporting_period": account["reporting_period"],
                "posting_date": date(period.year, period.month, posting_day).isoformat(),
                "transaction_type": transaction_type, "transaction_status": status,
                "amount": transaction_amount(rng, transaction_type), "currency_code": "EUR",
            }
            rows.append(row)
            transaction_number += 1
            if status == "POSTED" and transaction_type in ELIGIBLE_TRANSACTION_TYPES:
                eligible_counts[(branch, account["reporting_period"])] = eligible_counts.get((branch, account["reporting_period"]), 0) + 1

    prior_key = ("B018", "2025-04-30")
    spike_key = ("B018", "2025-05-31")
    target = max(1, int(eligible_counts.get(prior_key, 0) * 1.30) + 1)
    current = eligible_counts.get(spike_key, 0)
    spike_accounts = account_by_branch_period[spike_key]
    while current < target:
        account = rng.choice(spike_accounts)
        transaction_type = rng.choice(ELIGIBLE_TRANSACTION_TYPES)
        rows.append({
            "transaction_id": f"T{transaction_number:09d}",
            "account_id": account["account_id"], "reporting_period": "2025-05-31",
            "posting_date": f"2025-05-{rng.randint(1, 31):02d}",
            "transaction_type": transaction_type, "transaction_status": "POSTED",
            "amount": transaction_amount(rng, transaction_type), "currency_code": "EUR",
        })
        transaction_number += 1
        current += 1
    return rows


def make_reporting_cycles(periods: list[date]) -> list[dict]:
    rows = []
    for period in periods:
        stage_dates = {stage: add_working_days(period, stage) for stage in range(1, 6)}
        blocked = period == date(2025, 10, 31)
        rows.append({
            "reporting_period": period.isoformat(),
            "extract_status": "COMPLETE", "extract_completed_at": f"{stage_dates[1].isoformat()}T17:00:00",
            "validation_status": "BLOCKED" if blocked else "COMPLETE",
            "validation_completed_at": stage_dates[2].isoformat() + "T16:00:00",
            "branch_review_status": "BLOCKED" if blocked else "COMPLETE",
            "branch_review_completed_at": None if blocked else stage_dates[3].isoformat() + "T16:00:00",
            "correction_status": "BLOCKED" if blocked else "COMPLETE",
            "correction_completed_at": None if blocked else stage_dates[4].isoformat() + "T16:00:00",
            "report_status": "BLOCKED" if blocked else "COMPLETE",
            "report_completed_at": None if blocked else stage_dates[5].isoformat() + "T12:00:00",
            "publication_blocked": 1 if blocked else 0,
            "overall_dq_exception_rate": None,
        })
    return rows


def make_critical_fixtures() -> list[dict]:
    return [
        {"fixture_id": "INJ-C01", "source_table": "customer_period_assignments", "record_key": "C00001|2025-10-31", "raw_payload": '{"customer_id":"C00001","reporting_period":"2025-10-31","home_branch_id":null}'},
        {"fixture_id": "INJ-C02", "source_table": "transactions", "record_key": "T_BAD_001", "raw_payload": '{"transaction_id":"T_BAD_001","account_id":"A000001","reporting_period":null}'},
        {"fixture_id": "INJ-C03", "source_table": "customers", "record_key": "C00001", "raw_payload": '{"customer_id":"C00001","customer_created_date":"2020-01-01","customer_status":"ACTIVE"}'},
        {"fixture_id": "INJ-C04", "source_table": "accounts", "record_key": "A_BAD_001|2025-10-31", "raw_payload": '{"account_id":"A_BAD_001","reporting_period":"2025-10-31","customer_id":"C99999"}'},
        {"fixture_id": "INJ-C05", "source_table": "loans", "record_key": "L_BAD_001|2025-10-31", "raw_payload": '{"loan_id":"L_BAD_001","reporting_period":"2025-10-31","customer_id":"C00001","outstanding_principal":-1250.00}'},
        {"fixture_id": "INJ-C06", "source_table": "monthly_branch_kpis", "record_key": "B001|2025-10-31|ACTIVE_CUSTOMERS", "raw_payload": '[{"branch_id":"B001","reporting_period":"2025-10-31","kpi_id":"ACTIVE_CUSTOMERS"},{"branch_id":"B001","reporting_period":"2025-10-31","kpi_id":"ACTIVE_CUSTOMERS"}]'},
    ]


def validate_critical_fixtures(fixtures: list[dict], accepted_data: dict[str, list[dict]]) -> list[dict]:
    """Run pre-load rules and create issues from detected fixture contents."""
    descriptions = {
        "MISSING_BRANCH_ID": "Customer-period assignment has no home branch.",
        "MISSING_REPORTING_PERIOD": "Transaction has no reporting period.",
        "DUPLICATE_PRIMARY_IDENTIFIER": "Customer identifier appears more than once in the raw input.",
        "INVALID_CUSTOMER_RELATIONSHIP": "Account references a customer that does not exist.",
        "NEGATIVE_OUTSTANDING_BALANCE": "Loan outstanding principal is negative.",
        "DUPLICATE_BRANCH_MONTH_KPI": "Derived output contains a duplicate branch-period-KPI key.",
    }
    customer_ids = {row["customer_id"] for row in accepted_data["customers"]}
    issues = []
    for fixture in fixtures:
        payload = json.loads(fixture["raw_payload"])
        source_table = fixture["source_table"]
        rule_code = None
        if source_table == "customer_period_assignments" and payload.get("home_branch_id") is None:
            rule_code = "MISSING_BRANCH_ID"
        elif source_table == "transactions" and payload.get("reporting_period") is None:
            rule_code = "MISSING_REPORTING_PERIOD"
        elif source_table == "customers" and payload.get("customer_id") in customer_ids:
            rule_code = "DUPLICATE_PRIMARY_IDENTIFIER"
        elif source_table == "accounts" and payload.get("customer_id") not in customer_ids:
            rule_code = "INVALID_CUSTOMER_RELATIONSHIP"
        elif source_table == "loans" and payload.get("outstanding_principal", 0) < 0:
            rule_code = "NEGATIVE_OUTSTANDING_BALANCE"
        elif source_table == "monthly_branch_kpis":
            keys = [(row.get("branch_id"), row.get("reporting_period"), row.get("kpi_id")) for row in payload]
            if len(keys) != len(set(keys)):
                rule_code = "DUPLICATE_BRANCH_MONTH_KPI"
        if rule_code is None:
            raise AssertionError(f"Critical fixture was not detected: {fixture}")
        issues.append({
            "issue_id": fixture["fixture_id"], "reporting_period": "2025-10-31",
            "source_table": source_table, "record_key": fixture["record_key"],
            "rule_code": rule_code, "severity": "CRITICAL",
            "issue_description": descriptions[rule_code], "detected_at": GENERATED_AT,
            "issue_status": "OPEN", "assigned_owner": "Data Owner",
            "resolution_note": None, "resolved_at": None,
        })
    return issues


def build_data() -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    periods = reporting_periods()
    branches = make_branches()
    customers, created_dates = make_customers(rng, periods)
    assignments, assignment_lookup = make_assignments(rng, periods, created_dates)
    account_masters = make_account_masters(rng, periods, created_dates)
    accounts = make_accounts(rng, periods, account_masters, assignment_lookup)
    loan_masters = make_loan_masters(rng, assignment_lookup)
    loans = make_loans(rng, periods, loan_masters, assignment_lookup)
    transactions = make_transactions(rng, accounts, assignment_lookup)
    cycles = make_reporting_cycles(periods)
    fixtures = make_critical_fixtures()
    data = {
        "branches": branches,
        "customers": customers,
        "customer_period_assignments": assignments,
        "accounts": accounts,
        "loans": loans,
        "transactions": transactions,
        "reporting_cycle_status": cycles,
        "validation_issues": [],
        "reporting_adjustments": [],
        "monthly_branch_kpis": [],
        "injected_critical_records": fixtures,
    }
    data["validation_issues"] = validate_critical_fixtures(fixtures, data)
    return data


def rows_hash(data: dict[str, list[dict]]) -> str:
    digest = hashlib.sha256()
    for table_name in sorted(data):
        digest.update(table_name.encode())
        for row in data[table_name]:
            digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fieldnames:
        return
    columns = fieldnames or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


TABLE_ORDER = [
    "branches", "customers", "customer_period_assignments", "accounts", "loans",
    "transactions", "reporting_cycle_status", "monthly_branch_kpis",
    "validation_issues", "reporting_adjustments",
]


def write_outputs(data: dict[str, list[dict]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    fields_for_empty = {
        "monthly_branch_kpis": ["branch_id", "reporting_period", "kpi_id", "calculated_value", "reported_value", "calculated_at", "result_status"],
        "reporting_adjustments": ["adjustment_id", "branch_id", "reporting_period", "kpi_id", "original_value", "adjusted_value", "reason", "approver", "approval_date", "status", "created_at"],
    }
    for table_name in TABLE_ORDER:
        write_csv(RAW_DIR / f"{table_name}.csv", data[table_name], fields_for_empty.get(table_name))
    write_csv(RAW_DIR / "injected_critical_records.csv", data["injected_critical_records"])

    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for table_name in TABLE_ORDER:
            rows = data[table_name]
            if not rows:
                continue
            columns = list(rows[0])
            placeholders = ", ".join(["?"] * len(columns))
            connection.executemany(
                f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
                [[row[column] for column in columns] for row in rows],
            )
        connection.commit()
    finally:
        connection.close()


def verify_database(data: dict[str, list[dict]]) -> dict:
    checks = {}
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        checks["foreign_key_violations"] = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        checks["row_counts"] = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLE_ORDER
        }
        checks["period_count"] = connection.execute("SELECT COUNT(DISTINCT reporting_period) FROM reporting_cycle_status").fetchone()[0]
        checks["period_min_max"] = list(connection.execute("SELECT MIN(reporting_period), MAX(reporting_period) FROM reporting_cycle_status").fetchone())
        checks["branch_count"] = connection.execute("SELECT COUNT(*) FROM branches").fetchone()[0]
        checks["assignment_duplicate_keys"] = connection.execute(
            "SELECT COUNT(*) FROM (SELECT customer_id, reporting_period, COUNT(*) n FROM customer_period_assignments GROUP BY customer_id, reporting_period HAVING n > 1)"
        ).fetchone()[0]
        checks["negative_valid_loan_balances"] = connection.execute("SELECT COUNT(*) FROM loans WHERE outstanding_principal < 0").fetchone()[0]
        checks["negative_current_balance_rows"] = connection.execute(
            "SELECT COUNT(*) FROM accounts WHERE product_category = 'CURRENT' AND month_end_balance < 0"
        ).fetchone()[0]
        checks["critical_fixture_count"] = len(data["injected_critical_records"])
        checks["open_critical_issue_count"] = connection.execute(
            "SELECT COUNT(*) FROM validation_issues WHERE severity = 'CRITICAL' AND issue_status = 'OPEN'"
        ).fetchone()[0]
        checks["blocked_cycle_count"] = connection.execute(
            "SELECT COUNT(*) FROM reporting_cycle_status WHERE publication_blocked = 1"
        ).fetchone()[0]
        checks["weekend_stage_timestamp_count"] = connection.execute(
            """
            SELECT COUNT(*) FROM reporting_cycle_status
            WHERE (extract_completed_at IS NOT NULL AND strftime('%w', substr(extract_completed_at, 1, 10)) IN ('0', '6'))
               OR (validation_completed_at IS NOT NULL AND strftime('%w', substr(validation_completed_at, 1, 10)) IN ('0', '6'))
               OR (branch_review_completed_at IS NOT NULL AND strftime('%w', substr(branch_review_completed_at, 1, 10)) IN ('0', '6'))
               OR (correction_completed_at IS NOT NULL AND strftime('%w', substr(correction_completed_at, 1, 10)) IN ('0', '6'))
               OR (report_completed_at IS NOT NULL AND strftime('%w', substr(report_completed_at, 1, 10)) IN ('0', '6'))
            """
        ).fetchone()[0]
        checks["detected_critical_rule_codes"] = [
            row[0] for row in connection.execute(
                "SELECT rule_code FROM validation_issues WHERE severity = 'CRITICAL' ORDER BY issue_id"
            )
        ]
        checks["logical_account_count"] = connection.execute("SELECT COUNT(DISTINCT account_id) FROM accounts").fetchone()[0]
        checks["logical_loan_count"] = connection.execute("SELECT COUNT(DISTINCT loan_id) FROM loans").fetchone()[0]
        checks["controlled_account_products"] = [row[0] for row in connection.execute("SELECT DISTINCT product_category FROM accounts ORDER BY 1")]
        checks["controlled_loan_products"] = [row[0] for row in connection.execute("SELECT DISTINCT loan_category FROM loans ORDER BY 1")]
        checks["controlled_transaction_statuses"] = [row[0] for row in connection.execute("SELECT DISTINCT transaction_status FROM transactions ORDER BY 1")]
    finally:
        connection.close()
    return checks


def verify_warning_scenarios(data: dict[str, list[dict]]) -> dict:
    """Calculate only the small KPI subset needed to verify injected warnings."""
    assignment = {
        (row["customer_id"], row["reporting_period"]): row["home_branch_id"]
        for row in data["customer_period_assignments"]
    }
    deposit = {}
    active_customers = {}
    first_eligible_open = {}
    for row in data["accounts"]:
        period = date.fromisoformat(row["reporting_period"])
        opened = date.fromisoformat(row["open_date"])
        closed = date.fromisoformat(row["close_date"]) if row["close_date"] else None
        if row["product_category"] not in {"CURRENT", "SAVINGS"} or not is_open(opened, closed, period):
            continue
        key = (row["customer_id"], row["reporting_period"])
        branch = assignment[key]
        active_customers.setdefault((branch, row["reporting_period"]), set()).add(row["customer_id"])
        if row["month_end_balance"] > 0:
            deposit[(branch, row["reporting_period"])] = deposit.get((branch, row["reporting_period"]), 0) + row["month_end_balance"]
        existing = first_eligible_open.get(row["customer_id"])
        first_eligible_open[row["customer_id"]] = opened if existing is None else min(existing, opened)

    new_customers = {}
    for customer_id, opened in first_eligible_open.items():
        period = period_for_day(opened).isoformat()
        if (customer_id, period) in assignment:
            branch = assignment[(customer_id, period)]
            new_customers[(branch, period)] = new_customers.get((branch, period), 0) + 1

    loan_portfolio = {}
    default_balance = {}
    for row in data["loans"]:
        period = date.fromisoformat(row["reporting_period"])
        opened = date.fromisoformat(row["open_date"])
        closed = date.fromisoformat(row["close_date"]) if row["close_date"] else None
        if not is_open(opened, closed, period):
            continue
        branch = assignment[(row["customer_id"], row["reporting_period"])]
        key = (branch, row["reporting_period"])
        loan_portfolio[key] = loan_portfolio.get(key, 0) + row["outstanding_principal"]
        if row["loan_status"] == "DEFAULT":
            default_balance[key] = default_balance.get(key, 0) + row["outstanding_principal"]

    transaction_count = {}
    account_customer = {(row["account_id"], row["reporting_period"]): row["customer_id"] for row in data["accounts"]}
    for row in data["transactions"]:
        if row["transaction_status"] != "POSTED" or row["transaction_type"] not in ELIGIBLE_TRANSACTION_TYPES:
            continue
        customer_id = account_customer[(row["account_id"], row["reporting_period"])]
        branch = assignment[(customer_id, row["reporting_period"])]
        key = (branch, row["reporting_period"])
        transaction_count[key] = transaction_count.get(key, 0) + 1

    def movement(values: dict, branch: str, current: str, previous: str) -> float | None:
        prior = values.get((branch, previous))
        if prior in (None, 0):
            return None
        current_value = values.get((branch, current), 0)
        return (current_value - prior) / prior * 100

    active_counts = {key: len(value) for key, value in active_customers.items()}
    deposit_move = movement(deposit, "B020", "2025-03-31", "2025-02-28")
    loan_move = movement(loan_portfolio, "B019", "2025-04-30", "2025-03-31")
    transaction_move = movement(transaction_count, "B018", "2025-05-31", "2025-04-30")
    new_customer_move = movement(new_customers, "B017", "2025-06-30", "2025-05-31")
    active_move = movement(active_counts, "B016", "2025-07-31", "2025-06-30")
    default_total = default_balance.get(("B015", "2025-08-31"), 0)
    portfolio_total = loan_portfolio.get(("B015", "2025-08-31"), 0)
    default_rate = default_total / portfolio_total * 100 if portfolio_total else None
    zero_transactions = transaction_count.get(("B014", "2025-09-30"), 0)

    result = {
        "deposit_volume_b020_2025_03_mom_pct": deposit_move,
        "loan_portfolio_b019_2025_04_mom_pct": loan_move,
        "transaction_count_b018_2025_05_mom_pct": transaction_move,
        "new_customers_b017_2025_06_mom_pct": new_customer_move,
        "active_customers_b016_2025_07_mom_pct": active_move,
        "default_rate_b015_2025_08_pct": default_rate,
        "transaction_count_b014_2025_09": zero_transactions,
    }
    expected = {
        "deposit_volume": deposit_move is not None and abs(deposit_move) > 20,
        "loan_portfolio": loan_move is not None and abs(loan_move) > 20,
        "transaction_count_movement": transaction_move is not None and abs(transaction_move) > 20,
        "new_customers": new_customer_move is not None and abs(new_customer_move) > 20,
        "active_customers": active_move is not None and abs(active_move) > 10,
        "default_rate": default_rate is not None and default_rate > 8,
        "zero_transaction_activity": zero_transactions == 0,
    }
    result["expected_warning_rules_triggered"] = expected
    if not all(expected.values()):
        raise AssertionError(f"One or more designed warning scenarios did not trigger: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-repeatability", action="store_true")
    args = parser.parse_args()

    data = build_data()
    first_hash = rows_hash(data)
    if args.verify_repeatability:
        second_hash = rows_hash(build_data())
        if first_hash != second_hash:
            raise AssertionError("Repeatability check failed")
    write_outputs(data)
    checks = verify_database(data)
    expected_critical_rules = [
        "MISSING_BRANCH_ID", "MISSING_REPORTING_PERIOD", "DUPLICATE_PRIMARY_IDENTIFIER",
        "INVALID_CUSTOMER_RELATIONSHIP", "NEGATIVE_OUTSTANDING_BALANCE",
        "DUPLICATE_BRANCH_MONTH_KPI",
    ]
    if checks["detected_critical_rule_codes"] != expected_critical_rules:
        raise AssertionError("Critical fixtures did not produce the expected validation issues")
    if checks["weekend_stage_timestamp_count"] != 0:
        raise AssertionError("A reporting stage was scheduled on a weekend")
    checks["warning_scenario_verification"] = verify_warning_scenarios(data)
    checks["seed"] = SEED
    checks["canonical_data_sha256"] = first_hash
    checks["repeatability_verified"] = bool(args.verify_repeatability)
    manifest_path = PROCESSED_DIR / "generation_manifest.json"
    manifest_path.write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(checks, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
