from datetime import datetime, UTC

from app.db import init_db, get_db_connection
from app.schemas.tracker import (
    ApplicationRow,
    ApplicationRowCreateRequest,
    ApplicationRowResponse,
    ApplicationStatusUpdateRequest,
)


class TrackerService:
    def __init__(self) -> None:
        init_db()

    def add_row(self, payload: ApplicationRowCreateRequest) -> ApplicationRowResponse:
        now = datetime.now(UTC).isoformat()
        conn = get_db_connection()
        try:
            conn.execute(
                """
                INSERT INTO application_rows (
                    company_applied,
                    role,
                    salary_quoted_while_applying,
                    job_posted_on,
                    applied_using,
                    status,
                    link,
                    job_id,
                    base_match_percent,
                    tailored_match_percent,
                    resume_version_used,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_applied, role) DO UPDATE SET
                    salary_quoted_while_applying = excluded.salary_quoted_while_applying,
                    job_posted_on = excluded.job_posted_on,
                    applied_using = excluded.applied_using,
                    status = excluded.status,
                    link = excluded.link,
                    job_id = excluded.job_id,
                    base_match_percent = excluded.base_match_percent,
                    tailored_match_percent = excluded.tailored_match_percent,
                    resume_version_used = excluded.resume_version_used,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    payload.company_applied,
                    payload.role,
                    payload.salary_quoted_while_applying,
                    payload.job_posted_on,
                    payload.applied_using,
                    payload.status,
                    payload.link,
                    payload.job_id,
                    payload.base_match_percent,
                    payload.tailored_match_percent,
                    payload.resume_version_used,
                    payload.notes,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return ApplicationRowResponse(
            company_applied=payload.company_applied,
            role=payload.role,
            status=payload.status,
            message="Application row saved to SQLite.",
        )

    def update_status(self, payload: ApplicationStatusUpdateRequest) -> ApplicationRowResponse:
        now = datetime.now(UTC).isoformat()
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE application_rows
                SET status = ?, notes = ?, updated_at = ?
                WHERE company_applied = ? AND role = ?
                """,
                (
                    payload.status,
                    payload.notes,
                    now,
                    payload.company_applied,
                    payload.role,
                ),
            )

            if cursor.rowcount == 0:
                conn.execute(
                    """
                    INSERT INTO application_rows (
                        company_applied,
                        role,
                        salary_quoted_while_applying,
                        job_posted_on,
                        applied_using,
                        status,
                        link,
                        job_id,
                        base_match_percent,
                        tailored_match_percent,
                        resume_version_used,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.company_applied,
                        payload.role,
                        "N/A",
                        "Unknown",
                        "Company Website",
                        payload.status,
                        "",
                        None,
                        None,
                        None,
                        None,
                        payload.notes,
                        now,
                        now,
                    ),
                )

            conn.commit()
        finally:
            conn.close()

        return ApplicationRowResponse(
            company_applied=payload.company_applied,
            role=payload.role,
            status=payload.status,
            message="Application status updated in SQLite.",
        )

    def list_rows(self) -> list[ApplicationRow]:
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """
                SELECT
                    company_applied,
                    role,
                    salary_quoted_while_applying,
                    job_posted_on,
                    applied_using,
                    status,
                    link,
                    job_id,
                    base_match_percent,
                    tailored_match_percent,
                    resume_version_used,
                    notes
                FROM application_rows
                ORDER BY company_applied COLLATE NOCASE, role COLLATE NOCASE
                """
            ).fetchall()
        finally:
            conn.close()

        return [ApplicationRow(**dict(row)) for row in rows]