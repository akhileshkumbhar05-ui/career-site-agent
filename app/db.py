from pathlib import Path
import sqlite3

DB_PATH = Path("data/career_site_agent.db")


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
        conn.commit()
    finally:
        conn.close()