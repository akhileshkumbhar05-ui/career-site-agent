from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT_DIR / "n8n" / "workflows"

REQUIRED_WORKFLOWS = [
    "WF1_Manual_FastAPI_Discord_Test.json",
    "WF2_Incoming_Job_Lead_Processor.json",
    "WF3_Confirmed_Application_To_Sheets.json",
    "WF4_Gmail_Status_Monitor.json",
    "WF5_Email_Backfill_Scanner.json",
    "WF6_Queue_Worker_Scheduler.json",
    "WF7_Career_Agent_Orchestrator.json",
]

EXPECTED_ACTIVE_WORKFLOWS = [
    "WF2_Incoming_Job_Lead_Processor",
    "WF3_Confirmed_Application_To_Sheets",
    "WF4_Gmail_Status_Monitor",
    "WF5_Email_Backfill_Scanner",
    "WF7_Career_Agent_Orchestrator",
]

APPS_SCRIPT_URL_PATTERN = re.compile(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local production readiness for CareerSite Agent.")
    parser.add_argument("--skip-http", action="store_true", help="Skip localhost FastAPI and n8n checks.")
    parser.add_argument("--skip-live-apps-script", action="store_true", help="Skip live Google Apps Script deployment check.")
    parser.add_argument(
        "--skip-live-n8n",
        action="store_true",
        help="Skip live n8n workflow, Apps Script endpoint, and recent trigger-log checks.",
    )
    args = parser.parse_args()

    checks: list[tuple[str, str, str]] = []
    env = load_env(ROOT_DIR / ".env")

    checks.append(check_file("Root .env exists", ROOT_DIR / ".env"))
    checks.append(check_file("Apps Script source exists", ROOT_DIR / "google_cloud" / "Code.gs"))
    checks.append(check_file("Target companies file exists", ROOT_DIR / "data" / "target_companies.json"))
    checks.append(check_file("Email status rules exist", ROOT_DIR / "data" / "email_status_rules.json"))
    checks.append(check_file("Job search profile exists", ROOT_DIR / "data" / "job_search_profile.json"))
    checks.append(check_file("Application profile exists", ROOT_DIR / "data" / "application_profile.json"))
    checks.append(check_queue_components())
    checks.append(check_autofill_components())

    checks.extend(check_env(env))
    checks.extend(check_workflows())
    checks.append(check_apps_script())
    checks.append(check_target_companies())
    checks.append(check_email_status_rules())
    checks.append(check_job_search_profile())
    checks.append(check_application_profile())
    checks.append(check_agent_components())
    if not args.skip_live_apps_script:
        checks.append(check_live_apps_script(env))

    if not args.skip_http:
        checks.append(check_http_json("FastAPI health", "http://127.0.0.1:8000/health", expected_key="status"))
        checks.append(check_http("n8n UI", "http://127.0.0.1:5678"))
        if not args.skip_live_n8n:
            checks.extend(check_live_n8n())

    print_report(checks)
    return 1 if any(status == "FAIL" for status, _, _ in checks) else 0


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")

    return env


def check_env(env: dict[str, str]) -> list[tuple[str, str, str]]:
    checks = []

    checks.append(check_env_value(env, "GOOGLE_APPS_SCRIPT_URL", expected_prefix="https://script.google.com/macros/s/"))
    checks.append(check_env_value(env, "N8N_JOB_LEAD_WEBHOOK_URL", expected_prefix="http://localhost:5678/webhook/"))

    discord = env.get("DISCORD_WEBHOOK_URL", "")
    if discord and "REPLACE_WITH" not in discord:
        checks.append(("PASS", "Discord webhook configured", "Value present"))
    else:
        checks.append(("WARN", "Discord webhook configured", "Set DISCORD_WEBHOOK_URL or paste webhook URLs directly in n8n nodes"))

    return checks


def check_env_value(env: dict[str, str], key: str, expected_prefix: str) -> tuple[str, str, str]:
    value = env.get(key, "")
    if not value:
        return ("FAIL", f"{key} configured", "Missing from .env")
    if value.startswith("PASTE_") or "REPLACE_WITH" in value:
        return ("FAIL", f"{key} configured", "Still contains placeholder text")
    if not value.startswith(expected_prefix):
        return ("WARN", f"{key} configured", f"Unexpected prefix; expected {expected_prefix}")
    return ("PASS", f"{key} configured", "Value present")


def check_workflows() -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    for filename in REQUIRED_WORKFLOWS:
        path = WORKFLOW_DIR / filename
        if not path.exists():
            checks.append(("FAIL", f"{filename} exists", "Missing workflow export"))
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            checks.append(("FAIL", f"{filename} JSON", str(exc)))
            continue

        node_names = {node.get("name") for node in data.get("nodes", [])}
        missing_connections = []
        for source, groups in data.get("connections", {}).items():
            if source not in node_names:
                missing_connections.append(f"source:{source}")
            for branch in groups.get("main", []):
                for edge in branch:
                    target = edge.get("node")
                    if target not in node_names:
                        missing_connections.append(f"target:{target}")

        if missing_connections:
            checks.append(("FAIL", f"{filename} connections", ", ".join(missing_connections)))
        else:
            checks.append(("PASS", f"{filename} connections", f"{len(node_names)} nodes"))

        serialized = json.dumps(data)
        if "$env" in serialized:
            checks.append(("WARN", f"{filename} env expressions", "Contains $env; this n8n instance blocks env access in nodes"))

    return checks


def check_apps_script() -> tuple[str, str, str]:
    path = ROOT_DIR / "google_cloud" / "Code.gs"
    if not path.exists():
        return ("FAIL", "Code.gs capabilities", "Missing file")

    source = path.read_text(encoding="utf-8")
    version_match = re.search(r'const SCRIPT_VERSION = "([^"]+)"', source)
    required = [
        "Date",
        "Company Applied",
        "Salary Quoted while Applying",
        "status_update",
        "email_action",
        "Email Actions",
        "getAllowedStatusValues",
        "resolveAllowedStatus",
        "repair_job_validations",
        "human_confirmed_submission",
        "findExistingJobRow",
        "duplicate_skipped",
        "doGet",
    ]
    missing = [item for item in required if item not in source]
    if missing:
        return ("FAIL", "Code.gs capabilities", f"Missing markers: {', '.join(missing)}")

    version = version_match.group(1) if version_match else "unknown"
    return (
        "PASS",
        "Code.gs capabilities",
        f"{version}; confirmation-gated, duplicate-safe writer with validation repair and email action audit",
    )


def check_target_companies() -> tuple[str, str, str]:
    path = ROOT_DIR / "data" / "target_companies.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ("FAIL", "target_companies.json", str(exc))

    if not isinstance(data, list) or not data:
        return ("FAIL", "target_companies.json", "Expected a non-empty list")

    unsupported = [item for item in data if item.get("ats_type") not in {"ashby", "greenhouse", "lever"}]
    if unsupported:
        return ("WARN", "target_companies.json", f"{len(unsupported)} unsupported ats_type entries")

    return ("PASS", "target_companies.json", f"{len(data)} targets")


def check_email_status_rules() -> tuple[str, str, str]:
    path = ROOT_DIR / "data" / "email_status_rules.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ("FAIL", "email_status_rules.json", str(exc))

    statuses = data.get("status_options", [])
    rules = data.get("rules", [])
    if not statuses:
        return ("FAIL", "email_status_rules.json", "Missing status_options")
    if not rules:
        return ("FAIL", "email_status_rules.json", "Missing rules")

    missing_statuses = [
        rule.get("status")
        for rule in rules
        if rule.get("status") and rule.get("status") not in statuses
    ]
    if missing_statuses:
        return ("FAIL", "email_status_rules.json", f"Rules use unknown statuses: {', '.join(missing_statuses)}")

    return ("PASS", "email_status_rules.json", f"{len(statuses)} statuses, {len(rules)} rules")


def check_job_search_profile() -> tuple[str, str, str]:
    path = ROOT_DIR / "data" / "job_search_profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ("FAIL", "job_search_profile.json", str(exc))

    target_roles = data.get("target_roles", [])
    reject_terms = data.get("work_authorization", {}).get("reject_terms", [])
    output_root = data.get("resume_outputs", {}).get("root_directory", "")

    if not target_roles:
        return ("FAIL", "job_search_profile.json", "Missing target_roles")
    if not reject_terms:
        return ("FAIL", "job_search_profile.json", "Missing work authorization reject_terms")
    if not output_root:
        return ("FAIL", "job_search_profile.json", "Missing resume output root")

    return ("PASS", "job_search_profile.json", f"{len(target_roles)} target role groups; {len(reject_terms)} reject terms")


def check_application_profile() -> tuple[str, str, str]:
    path = ROOT_DIR / "data" / "application_profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ("FAIL", "application_profile.json", str(exc))

    work_auth = data.get("work_authorization", {})
    resume_storage = data.get("resume_storage", {})
    boundary = data.get("automation_boundary", {})

    if not work_auth.get("authorized_to_work_in_united_states"):
        return ("FAIL", "application_profile.json", "Work authorization field is missing or false")
    if not resume_storage.get("base_resume_pdf"):
        return ("FAIL", "application_profile.json", "Missing base_resume_pdf")
    if boundary.get("allow_final_submit") is not False:
        return ("WARN", "application_profile.json", "Final submit should stay manual unless explicitly changed")

    return ("PASS", "application_profile.json", "Work authorization, resume storage, and manual-submit boundary present")


def check_queue_components() -> tuple[str, str, str]:
    required = [
        ROOT_DIR / "app" / "schemas" / "queue.py",
        ROOT_DIR / "app" / "services" / "job_queue_service.py",
        ROOT_DIR / "app" / "services" / "application_orchestrator_service.py",
        ROOT_DIR / "app" / "api" / "queue.py",
        ROOT_DIR / "scripts" / "process_job_queue.py",
        ROOT_DIR / "scripts" / "queue_status_report.py",
    ]
    missing = [str(path.relative_to(ROOT_DIR)) for path in required if not path.exists()]
    if missing:
        return ("FAIL", "Queue/orchestrator components", f"Missing: {', '.join(missing)}")

    main_source = (ROOT_DIR / "app" / "main.py").read_text(encoding="utf-8")
    if "queue.router" not in main_source:
        return ("FAIL", "Queue/orchestrator components", "Queue router is not mounted in app/main.py")

    db_source = (ROOT_DIR / "app" / "db.py").read_text(encoding="utf-8")
    if "CREATE TABLE IF NOT EXISTS job_queue" not in db_source:
        return ("FAIL", "Queue/orchestrator components", "job_queue table is not initialized")

    scrape_source = (ROOT_DIR / "scripts" / "scrape_and_send_jobs.py").read_text(encoding="utf-8")
    for marker in ["apply_quality_gate", "--max-send", "--max-jobs-per-company", "--dry-run", "write_scrape_report"]:
        if marker not in scrape_source:
            return ("FAIL", "Queue/orchestrator components", f"Scrape control marker missing: {marker}")

    exporter_source = (ROOT_DIR / "app" / "services" / "application_packet_export_service.py").read_text(encoding="utf-8")
    if "apply_plan.json" not in exporter_source or "ats_answer_bank.md" not in exporter_source:
        return ("FAIL", "Queue/orchestrator components", "Application packet exporter is missing apply-plan artifacts")

    return ("PASS", "Queue/orchestrator components", "SQLite queue, leases, packet artifacts, API, worker, and report script present")


def check_autofill_components() -> tuple[str, str, str]:
    required = [
        ROOT_DIR / "app" / "schemas" / "ats_autofill.py",
        ROOT_DIR / "app" / "services" / "ats_autofill_service.py",
        ROOT_DIR / "app" / "services" / "autofill_context_service.py",
        ROOT_DIR / "app" / "api" / "autofill.py",
        ROOT_DIR / "scripts" / "ats_autofill_preview.py",
        ROOT_DIR / "browser_assist" / "ats_autofill_extension" / "manifest.json",
        ROOT_DIR / "browser_assist" / "ats_autofill_extension" / "content.js",
        ROOT_DIR / "browser_assist" / "ats_autofill_extension" / "background.js",
    ]
    missing = [str(path.relative_to(ROOT_DIR)) for path in required if not path.exists()]
    if missing:
        return ("FAIL", "Page watcher components", f"Missing: {', '.join(missing)}")

    main_source = (ROOT_DIR / "app" / "main.py").read_text(encoding="utf-8")
    if "autofill.router" not in main_source:
        return ("FAIL", "Page watcher components", "Autofill router is not mounted in app/main.py")

    extension_source = (ROOT_DIR / "browser_assist" / "ats_autofill_extension" / "content.js").read_text(
        encoding="utf-8"
    )
    for marker in ["CAREERSITE_WATCH", "looksLikeJobPage", "fillSuggestion", "Suggestions only", "sensitive"]:
        if marker not in extension_source:
            return ("FAIL", "Page watcher components", f"Watcher safety marker missing: {marker}")

    api_source = (ROOT_DIR / "app" / "api" / "autofill.py").read_text(encoding="utf-8")
    if "observe_page" not in api_source:
        return ("FAIL", "Page watcher components", "POST /autofill/observe watcher endpoint is missing")
    if "prepare_autofill_context" not in api_source:
        return ("FAIL", "Page watcher components", "POST /autofill/context preparation endpoint is missing")

    return ("PASS", "Page watcher components", "Watcher observe API, deterministic matcher, JD understanding, and Third Eye extension present")


def check_agent_components() -> tuple[str, str, str]:
    required = [
        ROOT_DIR / "app" / "schemas" / "agent.py",
        ROOT_DIR / "app" / "agents" / "job_discovery_agent.py",
        ROOT_DIR / "app" / "agents" / "fit_scoring_agent.py",
        ROOT_DIR / "app" / "agents" / "resume_tailoring_agent.py",
        ROOT_DIR / "app" / "agents" / "page_watcher_agent.py",
        ROOT_DIR / "app" / "agents" / "recruiter_outreach_agent.py",
        ROOT_DIR / "app" / "agents" / "tracker_email_agent.py",
        ROOT_DIR / "app" / "services" / "career_agent_orchestrator_service.py",
        ROOT_DIR / "app" / "api" / "agents.py",
        ROOT_DIR / "scripts" / "run_career_agents.py",
    ]
    missing = [str(path.relative_to(ROOT_DIR)) for path in required if not path.exists()]
    if missing:
        return ("FAIL", "AI agent components", f"Missing: {', '.join(missing)}")

    main_source = (ROOT_DIR / "app" / "main.py").read_text(encoding="utf-8")
    if "agents.router" not in main_source:
        return ("FAIL", "AI agent components", "Agents router is not mounted in app/main.py")

    agent_api = (ROOT_DIR / "app" / "api" / "agents.py").read_text(encoding="utf-8")
    for marker in [
        "/discover-jobs",
        "/score-fit",
        "/tailor-resume",
        "/observe",
        "/recruiter-outreach",
        "/track-email",
        "/run-pipeline",
    ]:
        if marker not in agent_api:
            return ("FAIL", "AI agent components", f"Missing API route marker: {marker}")

    return ("PASS", "AI agent components", "Discovery, scoring, tailoring, page watcher, recruiter, tracker, and orchestrator agents present")


def check_live_apps_script(env: dict[str, str]) -> tuple[str, str, str]:
    url = env.get("GOOGLE_APPS_SCRIPT_URL", "")
    if not url:
        return ("FAIL", "Live Apps Script deployment", "GOOGLE_APPS_SCRIPT_URL missing")

    try:
        with urllib.request.urlopen(f"{url}?target=status_options", timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return ("FAIL", "Live Apps Script deployment", str(exc.reason))
    except Exception as exc:
        return ("FAIL", "Live Apps Script deployment", str(exc))

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.DOTALL | re.IGNORECASE)
        plain = re.sub(r"<[^>]+>", " ", body)
        plain = re.sub(r"\s+", " ", plain).strip()
        return ("FAIL", "Live Apps Script deployment", plain[:180] or "Returned non-JSON response")

    if not payload.get("success"):
        return ("FAIL", "Live Apps Script deployment", payload.get("error", "status_options request failed"))

    statuses = payload.get("status_options") or []
    if not statuses:
        return ("FAIL", "Live Apps Script deployment", "No Status dropdown options returned")

    version = payload.get("script_version", "unknown")
    version_match = re.fullmatch(r"v(\d+)", str(version))
    if not version_match or int(version_match.group(1)) < 16:
        return ("FAIL", "Live Apps Script deployment", f"{version}; deploy Code.gs v16 or newer")
    return ("PASS", "Live Apps Script deployment", f"{version}; {len(statuses)} live dropdown statuses")


def check_live_n8n() -> list[tuple[str, str, str]]:
    container, container_error = find_n8n_container()
    if not container:
        return [("WARN", "Live n8n workflow definitions", container_error or "Running n8n container not found")]

    export_path = "/tmp/career-site-readiness-workflows.json"
    exported = run_command(
        ["docker", "exec", container, "n8n", "export:workflow", "--all", f"--output={export_path}"],
        timeout=30,
    )
    if exported.returncode != 0:
        return [("FAIL", "Live n8n workflow definitions", command_error(exported))]

    captured = run_command(["docker", "exec", container, "cat", export_path], timeout=10)
    if captured.returncode != 0:
        return [("FAIL", "Live n8n workflow definitions", command_error(captured))]

    try:
        workflows = json.loads(captured.stdout)
    except json.JSONDecodeError as exc:
        return [("FAIL", "Live n8n workflow definitions", f"Invalid exported JSON: {exc}")]

    checks = inspect_live_n8n_workflows(workflows)
    checks.extend(check_live_n8n_apps_script_endpoints(workflows))
    checks.append(check_recent_gmail_trigger_errors(container))
    return checks


def find_n8n_container() -> tuple[str | None, str | None]:
    configured = os.environ.get("N8N_CONTAINER_NAME", "").strip()
    listed = run_command(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"], timeout=10)
    if listed.returncode != 0:
        return None, f"Docker unavailable: {command_error(listed)}"

    containers: list[tuple[str, str]] = []
    for line in listed.stdout.splitlines():
        name, _, image = line.partition("\t")
        if name:
            containers.append((name.strip(), image.strip()))

    if configured:
        if any(name == configured for name, _ in containers):
            return configured, None
        return None, f"Configured n8n container is not running: {configured}"

    candidates = [name for name, image in containers if "n8n" in name.lower() or "n8n" in image.lower()]
    if not candidates:
        return None, "No running n8n Docker container found"
    if "n8n-n8n-1" in candidates:
        return "n8n-n8n-1", None
    return candidates[0], None


def inspect_live_n8n_workflows(workflows: object) -> list[tuple[str, str, str]]:
    if not isinstance(workflows, list):
        return [("FAIL", "Live n8n workflow definitions", "Expected an exported workflow list")]

    checks: list[tuple[str, str, str]] = []
    active_by_name: dict[str, list[dict]] = {}
    for workflow in workflows:
        if not isinstance(workflow, dict) or not workflow.get("active"):
            continue
        active_by_name.setdefault(str(workflow.get("name", "")), []).append(workflow)

    missing = [name for name in EXPECTED_ACTIVE_WORKFLOWS if not active_by_name.get(name)]
    duplicate = [name for name in EXPECTED_ACTIVE_WORKFLOWS if len(active_by_name.get(name, [])) > 1]
    if missing or duplicate:
        details = []
        if missing:
            details.append(f"missing/inactive: {', '.join(missing)}")
        if duplicate:
            details.append(f"multiple active copies: {', '.join(duplicate)}")
        checks.append(("FAIL", "Live n8n workflow activation", "; ".join(details)))
    else:
        checks.append(("PASS", "Live n8n workflow activation", f"{len(EXPECTED_ACTIVE_WORKFLOWS)} expected workflows active"))

    wf7_live = (active_by_name.get("WF7_Career_Agent_Orchestrator") or [None])[0]
    wf7_path = WORKFLOW_DIR / "WF7_Career_Agent_Orchestrator.json"
    try:
        wf7_repo = json.loads(wf7_path.read_text(encoding="utf-8"))
    except Exception as exc:
        checks.append(("FAIL", "Live WF7 protected parameters", f"Cannot read repo WF7: {exc}"))
        return checks

    if wf7_live is None:
        checks.append(("FAIL", "Live WF7 protected parameters", "Active WF7 not found"))
        return checks

    comparisons = [
        ("Run Career Agent Pipeline", "jsonBody"),
        ("Build Agent Run Summary", "jsCode"),
    ]
    mismatches: list[str] = []
    for node_name, parameter_name in comparisons:
        live_node = find_node(wf7_live, node_name)
        repo_node = find_node(wf7_repo, node_name)
        if not live_node or not repo_node:
            mismatches.append(f"missing node {node_name}")
            continue
        live_value = (live_node.get("parameters") or {}).get(parameter_name)
        repo_value = (repo_node.get("parameters") or {}).get(parameter_name)
        if live_value != repo_value:
            mismatches.append(f"{node_name}.{parameter_name}")

    if mismatches:
        checks.append(("FAIL", "Live WF7 protected parameters", f"Mismatch: {', '.join(mismatches)}"))
    else:
        checks.append(("PASS", "Live WF7 protected parameters", "Pipeline body and Discord summary match the repo"))
    return checks


def check_live_n8n_apps_script_endpoints(workflows: object) -> list[tuple[str, str, str]]:
    if not isinstance(workflows, list):
        return []

    owners: dict[str, set[str]] = {}
    for workflow in workflows:
        if not isinstance(workflow, dict) or not workflow.get("active"):
            continue
        name = str(workflow.get("name", "unnamed"))
        for url in extract_apps_script_urls(workflow):
            owners.setdefault(url, set()).add(name)

    if not owners:
        return [("WARN", "Live n8n Apps Script endpoints", "No direct Apps Script URLs found in active workflows")]

    expected_version = source_script_version()
    expected_statuses = expected_status_values()
    checks: list[tuple[str, str, str]] = []
    for url, workflow_names in sorted(owners.items(), key=lambda item: endpoint_fingerprint(item[0])):
        label = f"Live n8n Apps Script {endpoint_fingerprint(url)}"
        owner_detail = ", ".join(sorted(workflow_names))
        checks.append(check_apps_script_endpoint(label, url, expected_version, expected_statuses, owner_detail))
    return checks


def check_apps_script_endpoint(
    label: str,
    url: str,
    expected_version: str,
    expected_statuses: list[str],
    owner_detail: str,
) -> tuple[str, str, str]:
    separator = "&" if "?" in url else "?"
    probe_url = f"{url}{separator}target=status_options&readiness={time.time_ns()}"
    try:
        with urllib.request.urlopen(probe_url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return ("FAIL", label, f"{owner_detail}; request failed: {exc.reason}")
    except Exception as exc:
        return ("FAIL", label, f"{owner_detail}; invalid response: {exc}")

    version = str(payload.get("script_version", "unknown"))
    if version_number(version) < version_number(expected_version):
        return ("FAIL", label, f"{owner_detail}; serves {version}, expected {expected_version} or newer")

    statuses = payload.get("status_options") or []
    missing = [status for status in expected_statuses if status not in statuses]
    extra = [status for status in statuses if status not in expected_statuses]
    if missing:
        return ("FAIL", label, f"{owner_detail}; missing controlled statuses: {', '.join(missing)}")
    if extra:
        return ("WARN", label, f"{owner_detail}; {version}; unexpected statuses: {', '.join(extra)}")
    return ("PASS", label, f"{owner_detail}; {version}; {len(statuses)} controlled statuses")


def check_recent_gmail_trigger_errors(container: str) -> tuple[str, str, str]:
    logs = run_command(["docker", "logs", "--since", "6m", container], timeout=10)
    if logs.returncode != 0:
        return ("WARN", "Recent Gmail Trigger polling", command_error(logs))
    combined = f"{logs.stdout}\n{logs.stderr}"
    failures = len(re.findall(r"problem in ['\"]Gmail Trigger['\"]", combined, flags=re.IGNORECASE))
    if failures:
        return ("FAIL", "Recent Gmail Trigger polling", f"{failures} error(s) in the last 6 minutes")
    return ("PASS", "Recent Gmail Trigger polling", "No errors in the last 6 minutes")


def extract_apps_script_urls(workflow: dict) -> set[str]:
    serialized = json.dumps(workflow.get("nodes", []), ensure_ascii=True)
    return set(APPS_SCRIPT_URL_PATTERN.findall(serialized))


def find_node(workflow: dict, name: str) -> dict | None:
    return next((node for node in workflow.get("nodes", []) if node.get("name") == name), None)


def source_script_version() -> str:
    source = (ROOT_DIR / "google_cloud" / "Code.gs").read_text(encoding="utf-8")
    match = re.search(r'const SCRIPT_VERSION = "([^"]+)"', source)
    return match.group(1) if match else "v0"


def expected_status_values() -> list[str]:
    path = ROOT_DIR / "data" / "email_status_rules.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [str(value) for value in payload.get("status_options", [])]


def version_number(value: str) -> int:
    match = re.fullmatch(r"v(\d+)", value)
    return int(match.group(1)) if match else -1


def endpoint_fingerprint(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            decode_command_output(exc.stdout),
            decode_command_output(exc.stderr) or "Command timed out",
        )


def command_error(result: subprocess.CompletedProcess[str]) -> str:
    detail = decode_command_output(result.stderr or result.stdout or f"exit {result.returncode}").strip()
    return re.sub(r"\s+", " ", detail)[:180]


def decode_command_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def check_file(name: str, path: Path) -> tuple[str, str, str]:
    return ("PASS", name, str(path.relative_to(ROOT_DIR))) if path.exists() else ("FAIL", name, "Missing")


def check_http(name: str, url: str) -> tuple[str, str, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return ("PASS", name, f"HTTP {response.status}")
    except urllib.error.URLError as exc:
        return ("FAIL", name, str(exc.reason))
    except Exception as exc:
        return ("FAIL", name, str(exc))


def check_http_json(name: str, url: str, expected_key: str) -> tuple[str, str, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return ("FAIL", name, str(exc.reason))
    except Exception as exc:
        return ("FAIL", name, str(exc))

    if expected_key not in payload:
        return ("FAIL", name, f"Missing key {expected_key}")
    return ("PASS", name, json.dumps(payload))


def print_report(checks: list[tuple[str, str, str]]) -> None:
    width = max(len(name) for _, name, _ in checks) if checks else 10
    for status, name, detail in checks:
        print(f"[{status:<4}] {name:<{width}}  {detail}")

    failures = sum(1 for status, _, _ in checks if status == "FAIL")
    warnings = sum(1 for status, _, _ in checks if status == "WARN")
    print()
    print(f"Summary: {failures} failure(s), {warnings} warning(s)")


if __name__ == "__main__":
    sys.exit(main())
