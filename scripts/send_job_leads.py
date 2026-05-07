import json
from pathlib import Path

import requests


WEBHOOK_URL = "http://localhost:5678/webhook/incoming-job-lead"
INPUT_FILE = Path(__file__).with_name("sample_job_leads.json")
TIMEOUT_SECONDS = 30


def load_job_leads(file_path: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("sample_job_leads.json must contain a JSON list of job objects.")

    required_fields = {
        "job_id",
        "company",
        "title",
        "jd_text",
        "discovered_url",
        "source",
    }

    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Item #{i} is not a JSON object.")
        missing = required_fields - set(item.keys())
        if missing:
            raise ValueError(f"Item #{i} is missing required fields: {sorted(missing)}")

    return data


def send_job_lead(job: dict) -> None:
    response = requests.post(
        WEBHOOK_URL,
        json=job,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    print(f"[OK] {job['company']} - {job['title']}")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)


def main() -> None:
    jobs = load_job_leads(INPUT_FILE)
    print(f"Loaded {len(jobs)} job lead(s) from {INPUT_FILE}")

    for idx, job in enumerate(jobs, start=1):
        print(f"\n--- Sending job {idx}/{len(jobs)} ---")
        try:
            send_job_lead(job)
        except requests.RequestException as e:
            print(f"[FAILED] {job.get('company', 'Unknown')} - {job.get('title', 'Unknown')}")
            print(str(e))


if __name__ == "__main__":
    main()