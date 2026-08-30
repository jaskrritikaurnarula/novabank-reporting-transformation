"""Create reproducible Checkpoint 6 management tables, figures, and process maps."""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATPLOTLIB_CACHE = PROJECT_ROOT / "work" / "matplotlib"
MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MATPLOTLIB_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DATABASE_PATH = PROJECT_ROOT / "data" / "processed" / "novabank_reporting.db"
MANAGEMENT_DIR = PROJECT_ROOT / "management"
FIGURES_DIR = PROJECT_ROOT / "figures"
PROCESS_DIR = PROJECT_ROOT / "process"
LATEST_PERIOD = "2025-12-31"


def fetch_rows(connection: sqlite3.Connection, query: str, parameters=()):
    cursor = connection.execute(query, parameters)
    columns = [item[0] for item in cursor.description]
    return columns, [dict(zip(columns, row)) for row in cursor.fetchall()]


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def create_management_tables(connection: sqlite3.Connection) -> dict[str, list[dict]]:
    network_columns, network_rows = fetch_rows(
        connection,
        """
        WITH current_values AS (
            SELECT kpi_id, SUM(reported_value) AS total_value
            FROM monthly_branch_kpis
            WHERE reporting_period = ?
              AND kpi_id IN ('ACTIVE_CUSTOMERS', 'NEW_CUSTOMERS', 'DEPOSIT_VOLUME',
                             'LOAN_PORTFOLIO', 'TRANSACTION_COUNT')
            GROUP BY kpi_id
        ),
        weighted_default AS (
            SELECT
                SUM(d.reported_value * l.reported_value) / NULLIF(SUM(l.reported_value), 0) AS value
            FROM monthly_branch_kpis d
            JOIN monthly_branch_kpis l
              ON l.branch_id = d.branch_id
             AND l.reporting_period = d.reporting_period
             AND l.kpi_id = 'LOAN_PORTFOLIO'
            WHERE d.reporting_period = ? AND d.kpi_id = 'DEFAULT_RATE'
        ),
        network_loan_growth AS (
            SELECT 100.0 * (current_total - previous_total) / NULLIF(previous_total, 0) AS value
            FROM (
                SELECT
                    SUM(CASE WHEN reporting_period = ? THEN reported_value END) AS current_total,
                    SUM(CASE WHEN reporting_period = date(?, 'start of month', '-1 day')
                             THEN reported_value END) AS previous_total
                FROM monthly_branch_kpis
                WHERE kpi_id = 'LOAN_PORTFOLIO'
            )
        )
        SELECT ? AS reporting_period, kpi_id, total_value AS value FROM current_values
        UNION ALL SELECT ?, 'DEFAULT_RATE', value FROM weighted_default
        UNION ALL SELECT ?, 'MOM_LOAN_GROWTH', value FROM network_loan_growth
        ORDER BY kpi_id
        """,
        (LATEST_PERIOD,) * 3 + (LATEST_PERIOD,) + (LATEST_PERIOD,) * 3,
    )

    comparison_columns, comparison_rows = fetch_rows(
        connection,
        """
        WITH selected AS (
            SELECT branch_id, reporting_period, kpi_id, reported_value,
                   LAG(reported_value) OVER (
                       PARTITION BY branch_id, kpi_id ORDER BY reporting_period
                   ) AS previous_month_value
            FROM monthly_branch_kpis
            WHERE kpi_id IN ('ACTIVE_CUSTOMERS', 'DEPOSIT_VOLUME',
                             'LOAN_PORTFOLIO', 'DEFAULT_RATE')
        ),
        latest AS (
            SELECT *,
                   AVG(reported_value) OVER (PARTITION BY reporting_period, kpi_id)
                       AS average_branch_value,
                   RANK() OVER (
                       PARTITION BY reporting_period, kpi_id ORDER BY reported_value DESC
                   ) AS kpi_value_rank
            FROM selected
            WHERE reporting_period = ?
        )
        SELECT branch_id, reporting_period, kpi_id, reported_value,
               average_branch_value, previous_month_value,
               CASE WHEN previous_month_value IS NULL OR previous_month_value = 0 THEN NULL
                    ELSE 100.0 * (reported_value - previous_month_value) / previous_month_value END
                   AS month_over_month_change_pct,
               kpi_value_rank
        FROM latest
        ORDER BY kpi_id, kpi_value_rank, branch_id
        """,
        (LATEST_PERIOD,),
    )

    warning_columns, warning_rows = fetch_rows(
        connection,
        """
        SELECT v.reporting_period, substr(v.record_key, 1, 4) AS branch_id,
               CASE
                   WHEN v.rule_code LIKE '%ACTIVE_CUSTOMERS%' THEN 'ACTIVE_CUSTOMERS'
                   WHEN v.rule_code LIKE '%DEFAULT_RATE%' THEN 'DEFAULT_RATE'
                   WHEN v.rule_code LIKE '%DEPOSIT_VOLUME%' THEN 'DEPOSIT_VOLUME'
                   WHEN v.rule_code LIKE '%LOAN_PORTFOLIO%' THEN 'LOAN_PORTFOLIO'
                   WHEN v.rule_code LIKE '%NEW_CUSTOMERS%' THEN 'NEW_CUSTOMERS'
                   ELSE 'TRANSACTION_COUNT'
               END AS kpi_id,
               v.rule_code, k.calculated_value, v.issue_description, v.issue_status,
               COALESCE(v.resolution_note, '') AS commentary
        FROM validation_issues v
        LEFT JOIN monthly_branch_kpis k
          ON v.record_key = k.branch_id || '|' || k.reporting_period || '|' || k.kpi_id
        WHERE v.severity = 'WARNING'
        ORDER BY v.reporting_period, branch_id, v.rule_code
        """,
    )

    adjustment_columns, adjustment_rows = fetch_rows(
        connection,
        """
        SELECT adjustment_id, branch_id, reporting_period, kpi_id,
               original_value, adjusted_value, reason, approver,
               approval_date, status
        FROM reporting_adjustments
        ORDER BY reporting_period, branch_id, kpi_id
        """,
    )

    outputs = {
        "network_overview": network_rows,
        "branch_comparison": comparison_rows,
        "management_exceptions": warning_rows,
        "reporting_adjustments": adjustment_rows,
    }
    for name, columns, rows in (
        ("network_overview", network_columns, network_rows),
        ("branch_comparison", comparison_columns, comparison_rows),
        ("management_exceptions", warning_columns, warning_rows),
        ("reporting_adjustments", adjustment_columns, adjustment_rows),
    ):
        write_csv(MANAGEMENT_DIR / f"{name}.csv", columns, rows)
    return outputs


def create_management_figures(connection: sqlite3.Connection) -> None:
    _, loan_trend = fetch_rows(
        connection,
        """SELECT reporting_period, SUM(reported_value) AS value
           FROM monthly_branch_kpis WHERE kpi_id='LOAN_PORTFOLIO'
           GROUP BY reporting_period ORDER BY reporting_period""",
    )
    fig, axis = plt.subplots(figsize=(10, 5))
    axis.plot([row["reporting_period"][:7] for row in loan_trend],
              [row["value"] / 1_000_000 for row in loan_trend], marker="o")
    axis.set(title="Network Loan Portfolio Trend", xlabel="Reporting month",
             ylabel="Loan portfolio (€ millions)")
    axis.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "network_loan_portfolio_trend.png", dpi=300)
    plt.close(fig)

    _, deposits = fetch_rows(
        connection,
        """SELECT branch_id, reported_value FROM monthly_branch_kpis
           WHERE reporting_period=? AND kpi_id='DEPOSIT_VOLUME'
           ORDER BY reported_value""",
        (LATEST_PERIOD,),
    )
    fig, axis = plt.subplots(figsize=(9, 7))
    axis.barh([row["branch_id"] for row in deposits],
              [row["reported_value"] / 1_000_000 for row in deposits])
    axis.set(title="Deposit Volume by Branch — December 2025",
             xlabel="Deposit volume (€ millions)", ylabel="Branch")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "branch_deposit_volume.png", dpi=300)
    plt.close(fig)

    _, defaults = fetch_rows(
        connection,
        """
        SELECT d.branch_id, d.reported_value AS default_rate,
               AVG(d.reported_value) OVER () AS average_branch_rate,
               SUM(d.reported_value*l.reported_value) OVER () /
                   SUM(l.reported_value) OVER () AS weighted_network_rate
        FROM monthly_branch_kpis d
        JOIN monthly_branch_kpis l
          ON l.branch_id=d.branch_id AND l.reporting_period=d.reporting_period
         AND l.kpi_id='LOAN_PORTFOLIO'
        WHERE d.reporting_period=? AND d.kpi_id='DEFAULT_RATE'
        ORDER BY d.reported_value
        """,
        (LATEST_PERIOD,),
    )
    fig, axis = plt.subplots(figsize=(9, 7))
    axis.barh([row["branch_id"] for row in defaults],
              [row["default_rate"] for row in defaults], label="Branch rate")
    axis.axvline(defaults[0]["average_branch_rate"], linestyle="--",
                 label="Average branch rate")
    axis.axvline(defaults[0]["weighted_network_rate"], linestyle=":",
                 label="Portfolio-weighted network rate")
    axis.set(title="Default Rate by Branch — December 2025",
             xlabel="Default rate (%)", ylabel="Branch")
    axis.legend()
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "branch_default_rate.png", dpi=300)
    plt.close(fig)

    _, warnings = fetch_rows(
        connection,
        """SELECT rule_code, COUNT(*) AS warning_count FROM validation_issues
           WHERE severity='WARNING' GROUP BY rule_code ORDER BY warning_count""",
    )
    short_labels = [row["rule_code"].replace("WARN_", "").replace("_", " ").title()
                    for row in warnings]
    fig, axis = plt.subplots(figsize=(10, 6))
    axis.barh(short_labels, [row["warning_count"] for row in warnings])
    axis.set(title="Management Warnings by Rule", xlabel="Warning issues", ylabel="Rule")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "management_warnings_by_rule.png", dpi=300)
    plt.close(fig)


def draw_process(path: Path, title: str, steps: list[str], notes: list[str]) -> None:
    fig, axis = plt.subplots(figsize=(14, 6))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title(title, fontsize=17, pad=18)
    columns = 5
    for index, step in enumerate(steps):
        row, column = divmod(index, columns)
        visual_column = column if row % 2 == 0 else columns - 1 - column
        x = 0.04 + visual_column * 0.195
        y = 0.68 - row * 0.42
        axis.text(x + 0.075, y, f"{index + 1}. {step}", ha="center", va="center", fontsize=9,
                  bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="black"))
        if index < len(steps) - 1:
            next_row, next_column = divmod(index + 1, columns)
            if next_row == row:
                direction = 1 if row % 2 == 0 else -1
                axis.annotate("", xy=(x + 0.075 + direction * 0.112, y),
                              xytext=(x + 0.075 + direction * 0.082, y),
                              arrowprops=dict(arrowstyle="->"))
            else:
                axis.annotate("", xy=(x + 0.075, y - 0.36), xytext=(x + 0.075, y - 0.06),
                              arrowprops=dict(arrowstyle="->"))
    axis.text(0.5, 0.04, "  •  ".join(notes), ha="center", va="bottom", fontsize=9,
              wrap=True, bbox=dict(boxstyle="round,pad=0.5", facecolor="mistyrose", edgecolor="black"))
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def create_process_maps() -> None:
    draw_process(
        PROCESS_DIR / "as_is_reporting.png",
        "AS-IS: Manual Monthly Branch Reporting",
        ["Source extracts", "Analyst downloads files", "Manual spreadsheet\nconsolidation",
         "Manual validation", "KPI calculation", "Draft branch results",
         "Email/spreadsheet\ncorrections", "Recalculation", "Management report"],
        ["Manual consolidation", "Inconsistent KPI logic", "Repeated corrections",
         "Poor traceability", "Late issue discovery", "Analyst dependency", "Reporting delay"],
    )
    draw_process(
        PROCESS_DIR / "to_be_reporting.png",
        "TO-BE: Controlled Monthly Reporting Workflow",
        ["T+1 Standardised\nsource extracts", "Controlled load", "T+2 Automated\nvalidation",
         "Critical / warning\nclassification", "Central reporting\ndataset",
         "Approved KPI\ncalculation", "T+3 Branch review", "T+4 Structured\nexception closure",
         "T+5 Management\nreport", "Period close / archive"],
        ["Monday–Friday working days", "Critical issues block publication",
         "Warnings require disposition", "Public holidays outside V1 scope"],
    )


def main() -> None:
    for directory in (MANAGEMENT_DIR, FIGURES_DIR, PROCESS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if not DATABASE_PATH.exists():
        raise FileNotFoundError("Run generate_synthetic_data.py and run_checkpoint5.py first.")
    with sqlite3.connect(DATABASE_PATH) as connection:
        create_management_tables(connection)
        create_management_figures(connection)
    create_process_maps()
    print("Checkpoint 6 management outputs and figures created.")


if __name__ == "__main__":
    main()
