from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.schemas.queue import JobQueueItem
from app.services.job_queue_service import JobQueueService


READY_STATUSES = {"packet_ready", "manual_review", "scored"}


def build_records(items: list[JobQueueItem]) -> list[dict]:
    records = []
    for item in items:
        pipeline = (item.result or {}).get("pipeline_result") or {}
        export = (item.result or {}).get("export_result") or {}
        records.append(
            {
                "queue_id": item.queue_id,
                "status": item.status,
                "company": item.job.company,
                "role": item.job.title,
                "job_id": item.job.job_id,
                "source": item.job.source,
                "location": item.job.location,
                "official_url": pipeline.get("official_url") or item.job.discovered_url,
                "decision": pipeline.get("decision", ""),
                "decision_reason": pipeline.get("decision_reason", ""),
                "base_score": pipeline.get("base_score"),
                "tailored_score": pipeline.get("tailored_score"),
                "packet_folder_path": export.get("packet_folder_path", ""),
                "tailored_resume_pdf_path": export.get("tailored_resume_pdf_path", ""),
                "tailored_resume_html_path": export.get("tailored_resume_html_path", ""),
                "apply_plan_path": export.get("apply_plan_path", ""),
                "ats_answers_path": export.get("ats_answers_path", ""),
                "outreach_path": export.get("outreach_path", ""),
                "error": item.error,
                "updated_at": item.updated_at,
            }
        )
    return records


def render_markdown(records: list[dict], *, created_at: str) -> str:
    counts = Counter(record["status"] for record in records)
    ready = [record for record in records if record["status"] in READY_STATUSES]
    blocked = [record for record in records if record["status"] in {"failed", "rejected"}]

    lines = [
        "# CareerSite Queue Status",
        "",
        f"- Created at: {created_at}",
        f"- Total items shown: {len(records)}",
        f"- Ready or reviewable: {len(ready)}",
        "",
        "## Counts",
    ]

    for status, count in sorted(counts.items()):
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## Ready To Review / Apply"])
    if not ready:
        lines.append("- No packet-ready or reviewable items in this report.")
    for record in ready:
        score = record["base_score"] if record["base_score"] is not None else "N/A"
        tailored = record["tailored_score"] if record["tailored_score"] is not None else "N/A"
        lines.extend(
            [
                f"### {record['company']} - {record['role']}",
                f"- Queue ID: {record['queue_id']}",
                f"- Status: {record['status']}",
                f"- Decision: {record['decision'] or 'N/A'}",
                f"- Score: {score} base / {tailored} tailored",
                f"- Link: {record['official_url']}",
                f"- Packet: {record['packet_folder_path'] or 'N/A'}",
                f"- Resume PDF: {record['tailored_resume_pdf_path'] or 'N/A'}",
                f"- Apply plan: {record['apply_plan_path'] or 'N/A'}",
                f"- Outreach draft: {record['outreach_path'] or 'N/A'}",
                f"- Reason: {record['decision_reason'] or 'N/A'}",
                "",
            ]
        )

    if blocked:
        lines.append("## Blocked / Rejected")
        for record in blocked:
            detail = record["error"] or record["decision_reason"] or "No detail recorded"
            lines.append(f"- {record['status']}: {record['company']} - {record['role']} | {detail}")

    return "\n".join(lines).rstrip() + "\n"


def write_report(records: list[dict], output_root: Path) -> dict:
    created_at = datetime.now(UTC).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / f"queue_status_{stamp}.json"
    markdown_path = output_root / f"queue_status_{stamp}.md"

    payload = {
        "created_at": created_at,
        "counts": dict(Counter(record["status"] for record in records)),
        "records": records,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(records, created_at=created_at), encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "total": len(records),
        "ready": len([record for record in records if record["status"] in READY_STATUSES]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a reviewable report of CareerSite queue items.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum queue items to include.")
    parser.add_argument("--status", default="", help="Optional queue status filter.")
    parser.add_argument(
        "--output-root",
        default="data/outputs/queue_reports",
        help="Directory where JSON and Markdown reports are written.",
    )
    args = parser.parse_args()

    queue = JobQueueService()
    items = queue.list_items(status=args.status or None, limit=args.limit)
    records = build_records(items)
    result = write_report(records, Path(args.output_root))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
