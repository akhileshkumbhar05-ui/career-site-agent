from pathlib import Path
import os
import sqlite3

DEFAULT_DB_PATH = Path("data/career_site_agent.db")
MEMORY_DB_URI = "file:career_site_agent_test?mode=memory&cache=shared"
_MEMORY_DB_ANCHOR: sqlite3.Connection | None = None


def get_db_path() -> Path:
    return Path(os.getenv("CAREER_SITE_AGENT_DB_PATH", str(DEFAULT_DB_PATH)))


def get_db_connection() -> sqlite3.Connection:
    global _MEMORY_DB_ANCHOR

    db_path = get_db_path()
    if str(db_path) == ":memory:":
        if _MEMORY_DB_ANCHOR is None:
            _MEMORY_DB_ANCHOR = sqlite3.connect(MEMORY_DB_URI, uri=True, check_same_thread=False)
            _MEMORY_DB_ANCHOR.row_factory = sqlite3.Row
        conn = sqlite3.connect(MEMORY_DB_URI, uri=True, check_same_thread=False)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS application_rows (
                company_applied TEXT NOT NULL,
                role TEXT NOT NULL,
                salary_quoted_while_applying TEXT NOT NULL,
                job_posted_on TEXT NOT NULL,
                applied_using TEXT NOT NULL,
                status TEXT NOT NULL,
                link TEXT NOT NULL,
                job_id TEXT,
                base_match_percent INTEGER,
                tailored_match_percent INTEGER,
                resume_version_used TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (company_applied, role)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_queue (
                queue_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                source_job_id TEXT NOT NULL,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                jd_text TEXT NOT NULL,
                discovered_url TEXT NOT NULL,
                source TEXT NOT NULL,
                posted_at TEXT,
                location TEXT,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 100,
                attempts INTEGER NOT NULL DEFAULT 0,
                locked_by TEXT,
                locked_until TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_queue_claim
            ON job_queue(status, priority, created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_queue_source_job_id
            ON job_queue(source_job_id)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS application_loop_batches (
                batch_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                requested_count INTEGER NOT NULL,
                imported_count INTEGER NOT NULL,
                duplicate_count INTEGER NOT NULL,
                invalid_count INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS application_loop_items (
                loop_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                canonical_job_url TEXT,
                normalized_company TEXT NOT NULL,
                normalized_role TEXT NOT NULL,
                item_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES application_loop_batches(batch_id)
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_application_loop_canonical_url
            ON application_loop_items(canonical_job_url)
            WHERE canonical_job_url IS NOT NULL AND canonical_job_url <> ''
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_application_loop_company_role
            ON application_loop_items(normalized_company, normalized_role)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS application_loop_batch_outcomes (
                batch_id TEXT NOT NULL,
                input_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                loop_id TEXT,
                input_json TEXT NOT NULL,
                PRIMARY KEY (batch_id, input_index),
                FOREIGN KEY (batch_id) REFERENCES application_loop_batches(batch_id),
                FOREIGN KEY (loop_id) REFERENCES application_loop_items(loop_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_application_loop_items_created
            ON application_loop_items(created_at DESC)
            """
        )
        conn.commit()
    finally:
        conn.close()
