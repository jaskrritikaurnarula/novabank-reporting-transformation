PRAGMA foreign_keys = ON;

CREATE TABLE branches (
    branch_id TEXT PRIMARY KEY,
    branch_name TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IN ('NORTH', 'SOUTH', 'EAST', 'WEST')),
    open_date TEXT NOT NULL,
    close_date TEXT,
    CHECK (close_date IS NULL OR close_date >= open_date)
);

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    customer_created_date TEXT NOT NULL,
    customer_status TEXT NOT NULL CHECK (customer_status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE customer_period_assignments (
    customer_id TEXT NOT NULL,
    reporting_period TEXT NOT NULL,
    home_branch_id TEXT NOT NULL,
    PRIMARY KEY (customer_id, reporting_period),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (home_branch_id) REFERENCES branches(branch_id)
);

CREATE TABLE accounts (
    account_id TEXT NOT NULL,
    reporting_period TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    product_category TEXT NOT NULL CHECK (
        product_category IN ('CURRENT', 'SAVINGS', 'TERM_DEPOSIT', 'SECURITIES')
    ),
    open_date TEXT NOT NULL,
    close_date TEXT,
    month_end_balance REAL NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'EUR' CHECK (currency_code = 'EUR'),
    PRIMARY KEY (account_id, reporting_period),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CHECK (close_date IS NULL OR close_date >= open_date)
);

CREATE TABLE loans (
    loan_id TEXT NOT NULL,
    reporting_period TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    loan_category TEXT NOT NULL CHECK (
        loan_category IN ('PERSONAL_LOAN', 'AUTO_LOAN', 'MORTGAGE')
    ),
    open_date TEXT NOT NULL,
    close_date TEXT,
    outstanding_principal REAL NOT NULL CHECK (outstanding_principal >= 0),
    loan_status TEXT NOT NULL CHECK (loan_status IN ('PERFORMING', 'DEFAULT', 'CLOSED')),
    currency_code TEXT NOT NULL DEFAULT 'EUR' CHECK (currency_code = 'EUR'),
    PRIMARY KEY (loan_id, reporting_period),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CHECK (close_date IS NULL OR close_date >= open_date)
);

CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    reporting_period TEXT NOT NULL,
    posting_date TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN (
        'CARD_PAYMENT', 'CASH_WITHDRAWAL', 'CASH_DEPOSIT',
        'TRANSFER_IN', 'TRANSFER_OUT', 'DIRECT_DEBIT',
        'REVERSAL', 'FEE', 'INTEREST', 'LOAN_DISBURSEMENT', 'LOAN_REPAYMENT'
    )),
    transaction_status TEXT NOT NULL CHECK (transaction_status IN ('POSTED', 'PENDING', 'DECLINED')),
    amount REAL NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'EUR' CHECK (currency_code = 'EUR'),
    FOREIGN KEY (account_id, reporting_period)
        REFERENCES accounts(account_id, reporting_period)
);

CREATE TABLE reporting_cycle_status (
    reporting_period TEXT PRIMARY KEY,
    extract_status TEXT NOT NULL CHECK (extract_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETE', 'BLOCKED')),
    extract_completed_at TEXT,
    validation_status TEXT NOT NULL CHECK (validation_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETE', 'BLOCKED')),
    validation_completed_at TEXT,
    branch_review_status TEXT NOT NULL CHECK (branch_review_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETE', 'BLOCKED')),
    branch_review_completed_at TEXT,
    correction_status TEXT NOT NULL CHECK (correction_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETE', 'BLOCKED')),
    correction_completed_at TEXT,
    report_status TEXT NOT NULL CHECK (report_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETE', 'BLOCKED')),
    report_completed_at TEXT,
    publication_blocked INTEGER NOT NULL DEFAULT 0 CHECK (publication_blocked IN (0, 1)),
    overall_dq_exception_rate REAL CHECK (
        overall_dq_exception_rate IS NULL OR overall_dq_exception_rate BETWEEN 0 AND 100
    )
);

CREATE TABLE monthly_branch_kpis (
    branch_id TEXT NOT NULL,
    reporting_period TEXT NOT NULL,
    kpi_id TEXT NOT NULL CHECK (kpi_id IN (
        'ACTIVE_CUSTOMERS', 'NEW_CUSTOMERS', 'DEPOSIT_VOLUME',
        'LOAN_PORTFOLIO', 'DEFAULT_RATE', 'TRANSACTION_COUNT', 'MOM_LOAN_GROWTH'
    )),
    calculated_value REAL,
    reported_value REAL,
    calculated_at TEXT NOT NULL,
    result_status TEXT NOT NULL CHECK (result_status IN ('PRELIMINARY', 'FINAL')),
    PRIMARY KEY (branch_id, reporting_period, kpi_id),
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id),
    FOREIGN KEY (reporting_period) REFERENCES reporting_cycle_status(reporting_period)
);

CREATE TABLE validation_issues (
    issue_id TEXT PRIMARY KEY,
    reporting_period TEXT NOT NULL,
    source_table TEXT NOT NULL CHECK (source_table IN (
        'branches', 'customers', 'customer_period_assignments', 'accounts',
        'loans', 'transactions', 'monthly_branch_kpis', 'reporting_cycle_status'
    )),
    record_key TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('CRITICAL', 'WARNING')),
    issue_description TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    issue_status TEXT NOT NULL CHECK (issue_status IN ('OPEN', 'UNDER_REVIEW', 'RESOLVED', 'ACCEPTED_WARNING')),
    assigned_owner TEXT,
    resolution_note TEXT,
    resolved_at TEXT,
    FOREIGN KEY (reporting_period) REFERENCES reporting_cycle_status(reporting_period)
);

CREATE TABLE reporting_adjustments (
    adjustment_id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    reporting_period TEXT NOT NULL,
    kpi_id TEXT NOT NULL,
    original_value REAL NOT NULL,
    adjusted_value REAL NOT NULL,
    reason TEXT NOT NULL,
    approver TEXT,
    approval_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (branch_id, reporting_period, kpi_id)
        REFERENCES monthly_branch_kpis(branch_id, reporting_period, kpi_id),
    CHECK (
        status <> 'APPROVED'
        OR (approver IS NOT NULL AND approval_date IS NOT NULL)
    )
);

CREATE INDEX idx_assignments_branch_period
    ON customer_period_assignments(home_branch_id, reporting_period);
CREATE INDEX idx_accounts_customer_period
    ON accounts(customer_id, reporting_period);
CREATE INDEX idx_loans_customer_period
    ON loans(customer_id, reporting_period);
CREATE INDEX idx_transactions_account_period
    ON transactions(account_id, reporting_period);
CREATE INDEX idx_validation_period_severity
    ON validation_issues(reporting_period, severity);
