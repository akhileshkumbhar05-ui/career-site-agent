from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.scrapers.ats.greenhouse_scraper import GreenhouseScraper
from app.scrapers.job_lead_sender import JobLeadSender


WEBHOOK_URL = "http://localhost:5678/webhook/incoming-job-lead"
TARGETS_FILE = ROOT_DIR / "data" / "target_companies.json"


def load_targets(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("target_companies.json must contain a JSON list.")

    return data


def main() -> None:
    targets = load_targets(TARGETS_FILE)
    sender = JobLeadSender(webhook_url=WEBHOOK_URL)
    greenhouse = GreenhouseScraper()

    total_scraped = 0
    total_sent = 0

    for target in targets:
        company = target["company"]
        ats_type = target["ats_type"]
        board_url = target["url"]

        print(f"\n=== Scraping {company} [{ats_type}] ===")

        if ats_type != "greenhouse":
            print(f"[SKIP] Unsupported ats_type for now: {ats_type}")
            continue

        try:
            jobs = greenhouse.scrape_jobs(company=company, board_url=board_url)
        except Exception as e:
            print(f"[FAILED SCRAPE] {company}: {e}")
            continue

        print(f"Scraped {len(jobs)} job(s)")
        total_scraped += len(jobs)

        for job in jobs:
            try:
                sender.send_job_lead(job)
                print(f"[SENT] {job['company']} - {job['title']}")
                total_sent += 1
            except Exception as e:
                print(f"[FAILED SEND] {job['company']} - {job['title']}: {e}")

    print("\n=== Summary ===")
    print(f"Total scraped: {total_scraped}")
    print(f"Total sent:    {total_sent}")


if __name__ == "__main__":
    main()