import re
from datetime import datetime, UTC

import httpx

from app.config import settings
from app.db import init_db, get_db_connection
from app.schemas.tracker import (
    ApplicationRow,
    ApplicationRowCreateRequest,
    ApplicationRowResponse,
    ApplicationStatusUpdateRequest,
    SheetsLogRequest,
    SheetsLogResponse,
)


class TrackerService:
    def __init__(self) -> None:
        init_db()

    def log_to_sheets(self, payload: SheetsLogRequest) -> SheetsLogResponse:
        script_url = settings.google_apps_script_url
        if not script_url:
            return SheetsLogResponse(
                success=False,
                message="GOOGLE_APPS_SCRIPT_URL is not configured.",
            )

        role_for_tracking = self.format_role_for_tracking(payload.role, payload.job_id)

        sheets_payload = {
            "target": "jobs_applied",
            "date": payload.date,
            "company": payload.company,
            "role": role_for_tracking,
            "salary": payload.salary or "N/A",
            "job_posted_on": payload.job_posted_on or "Unknown",
            "applied_using": payload.applied_using or "Company Website",
            "status": payload.status or "Applied",
            "link": payload.link or "",
        }

        try:
            response = httpx.post(
                script_url,
                json=sheets_payload,
                timeout=30.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return SheetsLogResponse(
                success=False,
                message=f"Failed to reach Google Apps Script: {exc}",
            )

        if data.get("success"):
            self.add_row(
                ApplicationRowCreateRequest(
                    company_applied=payload.company,
                    role=role_for_tracking,
                    salary_quoted_while_applying=payload.salary or "N/A",
                    job_posted_on=payload.job_posted_on or "Unknown",
                    applied_using=payload.applied_using or "Company Website",
                    status=payload.status or "Applied",
                    link=payload.link or "",
                    job_id=payload.job_id,
                    base_match_percent=payload.base_match_percent,
                    tailored_match_percent=payload.tailored_match_percent,
                    resume_version_used=payload.resume_version_used,
                    notes=payload.notes,
                )
            )

        return SheetsLogResponse(
            success=bool(data.get("success")),
            message=data.get("error") or "Logged to Google Sheets.",
            script_version=data.get("script_version"),
            mode=data.get("mode"),
            target_row=data.get("target_row"),
        )

    def add_row(self, payload: ApplicationRowCreateRequest) -> ApplicationRowResponse:
        now = datetime.now(UTC).isoformat()
        role_for_tracking = self.format_role_for_tracking(payload.role, payload.job_id)
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
                    role_for_tracking,
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
            role=role_for_tracking,
            status=payload.status,
            message="Application row saved to SQLite.",
        )

    @staticmethod
    def format_role_for_tracking(role: str, job_id: str | None = None) -> str:
        role_text = (role or "").strip()
        job_id_text = (job_id or "").strip()

        if not job_id_text:
            return role_text

        role_lower = role_text.lower()
        job_id_lower = job_id_text.lower()

        if job_id_lower in role_lower:
            return role_text

        for token in re.findall(r"\(([^)]+)\)", role_text):
            normalized_token = token.strip().lower()
            if normalized_token and normalized_token in job_id_lower:
                return role_text

        if not role_text:
            return f"({job_id_text})"

        return f"{role_text} ({job_id_text})"

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
                    notes,
                    created_at,
                    updated_at
                FROM application_rows
                ORDER BY created_at DESC
                """
            ).fetchall()
        finally:
            conn.close()

        return [ApplicationRow(**dict(row)) for row in rows]
