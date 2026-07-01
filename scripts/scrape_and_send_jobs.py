from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.scrapers.ats.greenhouse_scraper import GreenhouseScraper
from app.scrapers.ats.lever_scraper import LeverScraper
from app.scrapers.job_lead_sender import JobLeadSender
from app.schemas.job import JobQualityGateRequest
from app.services.job_quality_gate_service import JobQualityGateService
from app.services.seen_jobs_store import SeenJobsStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("N8N_JOB_LEAD_WEBHOOK_URL", "http://localhost:5678/webhook/incoming-job-lead")
TARGETS_FILE = ROOT_DIR / "data" / "target_companies.json"
SCRAPE_DELAY_SECONDS = 2.0
DEFAULT_REPORT_DIR = ROOT_DIR / "data" / "outputs" / "scrape_reports"


def load_targets(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("target_companies.json must contain a JSON list.")

    return data


def apply_quality_gate(jobs: list[dict], quality_gate: JobQualityGateService) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    report_rows: list[dict] = []

    for job in jobs:
        result = quality_gate.evaluate(
            JobQualityGateRequest(
                company=job.get("company", ""),
                title=job.get("title", ""),
                jd_text=job.get("jd_text", ""),
                location=job.get("location"),
                source=job.get("source", "scraper"),
            )
        )
        report_rows.append(
            {
                "job_id": job.get("job_id", ""),
                "company": job.get("company", ""),
                "title": job.get("title", ""),
                "location": job.get("location", ""),
                "url": job.get("discovered_url", ""),
                "quality_decision": result.decision,
                "actionable": result.actionable,
                "role_key": result.role_key,
                "title_score": result.title_score,
                "keyword_score": result.keyword_score,
                "years_required": result.years_required,
                "experience_risk": result.experience_risk,
                "authorization_risk": result.authorization_risk,
                "reasons": result.reasons,
                "blockers": result.blockers,
                "signals": result.signals,
            }
        )
        if result.actionable:
            accepted.append(job)

    return accepted, report_rows


def write_scrape_report(report_rows: list[dict], summary: dict, report_dir: Path, target_rows: list[dict]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"scrape_report_{stamp}.json"
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "targets": target_rows,
        "jobs": report_rows,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape configured ATS targets and send quality-gated leads to n8n.")
    parser.add_argument("--targets-file", default=str(TARGETS_FILE), help="Path to target_companies.json.")
    parser.add_argument("--max-send", type=int, default=25, help="Maximum new actionable leads to send in one run.")
    parser.add_argument(
        "--max-jobs-per-company",
        type=int,
        default=25,
        help="Maximum scraped job descriptions to inspect per company.",
    )
    parser.add_argument("--delay-seconds", type=float, default=SCRAPE_DELAY_SECONDS, help="Delay between target companies.")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate and report leads without sending or marking seen.")
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory where scrape report JSON files are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets = load_targets(Path(args.targets_file))
    sender = JobLeadSender(webhook_url=WEBHOOK_URL)
    greenhouse = GreenhouseScraper()
    lever = LeverScraper()
    seen = SeenJobsStore()
    quality_gate = JobQualityGateService()

    evicted = seen.evict_old()
    if evicted:
        logger.info("Evicted %d old seen-job records", evicted)

    total_scraped = 0
    total_new = 0
    total_skipped = 0
    total_quality_rejected = 0
    total_sent = 0
    total_failed = 0
    report_rows: list[dict] = []
    target_rows: list[dict] = []

    for target in targets:
        if total_sent >= args.max_send:
            logger.info("Reached max-send cap of %d leads; stopping scrape.", args.max_send)
            break

        company = target["company"]
        ats_type = target["ats_type"]
        board_url = target.get("url", "")

        logger.info("Scraping %s [%s]", company, ats_type)
        target_row = {
            "company": company,
            "ats_type": ats_type,
            "url": board_url,
            "status": "started",
            "scraped": 0,
            "quality_rejected": 0,
            "seen_skipped": 0,
            "sent_or_would_send": 0,
            "error": "",
        }

        jobs: list[dict] = []

        try:
            if ats_type == "greenhouse":
                jobs = greenhouse.scrape_jobs(
                    company=company,
                    board_url=board_url,
                    source="Greenhouse Scraper",
                    max_jobs=args.max_jobs_per_company,
                )
            elif ats_type == "lever":
                lever_slug = target.get("lever_slug") or board_url.split("jobs.lever.co/")[-1].split("/")[0]
                jobs = lever.scrape_jobs(
                    company=company,
                    lever_slug=lever_slug,
                    source="Lever Scraper",
                    max_jobs=args.max_jobs_per_company,
                )
            else:
                logger.warning("Unsupported ats_type %s for %s", ats_type, company)
                continue
        except Exception as exc:
            logger.error("Scrape failed for %s: %s", company, exc)
            total_failed += 1
            target_row["status"] = "failed"
            target_row["error"] = str(exc)
            target_rows.append(target_row)
            continue

        total_scraped += len(jobs)
        target_row["scraped"] = len(jobs)
        logger.info("Scraped %d jobs from %s", len(jobs), company)

        actionable_jobs, quality_rows = apply_quality_gate(jobs, quality_gate)
        report_rows.extend(quality_rows)
        rejected = len(jobs) - len(actionable_jobs)
        total_quality_rejected += rejected
        target_row["quality_rejected"] = rejected
        if rejected:
            logger.info("Quality gate rejected %d jobs from %s", rejected, company)

        jobs_to_consider = actionable_jobs

        new_jobs = [job for job in jobs_to_consider if not seen.is_seen(job["job_id"])]
        skipped = len(jobs_to_consider) - len(new_jobs)
        total_skipped += skipped
        target_row["seen_skipped"] = skipped
        if skipped:
            logger.info("Skipping %d already-seen jobs from %s", skipped, company)

        remaining_capacity = max(0, args.max_send - total_sent)
        sent_for_target = 0
        for job in new_jobs[:remaining_capacity]:
            try:
                if args.dry_run:
                    logger.info("[DRY RUN] Would send %s - %s", job["company"], job["title"])
                else:
                    sender.send_job_lead(job)
                    seen.mark_seen(job["job_id"])
                    logger.info("[SENT] %s - %s", job["company"], job["title"])
                total_sent += 1
                total_new += 1
                sent_for_target += 1
            except Exception as exc:
                logger.error("[FAILED SEND] %s - %s: %s", job.get("company"), job.get("title"), exc)
                total_failed += 1

        target_row["sent_or_would_send"] = sent_for_target
        target_row["status"] = "ok"
        target_rows.append(target_row)
        time.sleep(args.delay_seconds)

    summary = {
        "dry_run": args.dry_run,
        "max_send": args.max_send,
        "total_scraped": total_scraped,
        "total_new": total_new,
        "total_seen_skipped": total_skipped,
        "total_quality_rejected": total_quality_rejected,
        "total_sent_or_would_send": total_sent,
        "total_failed": total_failed,
    }
    report_path = write_scrape_report(report_rows, summary, Path(args.report_dir), target_rows)

    logger.info("Total scraped          : %d", total_scraped)
    logger.info("Total new/actionable   : %d", total_new)
    logger.info("Total seen skipped     : %d", total_skipped)
    logger.info("Total quality rejected : %d", total_quality_rejected)
    logger.info("Total sent/would send  : %d", total_sent)
    logger.info("Total failed           : %d", total_failed)
    logger.info("Scrape report          : %s", report_path)


if __name__ == "__main__":
    main()
