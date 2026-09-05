import json
import subprocess

from scripts.check_production_readiness import (
    EXPECTED_ACTIVE_WORKFLOWS,
    ROOT_DIR,
    check_apps_script_endpoint,
    command_error,
    endpoint_fingerprint,
    expected_status_values,
    extract_apps_script_urls,
    inspect_live_n8n_workflows,
)


def test_live_n8n_inspection_accepts_expected_workflows_and_exact_wf7() -> None:
    wf7 = json.loads(
        (ROOT_DIR / "n8n" / "workflows" / "WF7_Career_Agent_Orchestrator.json").read_text(encoding="utf-8")
    )
    wf7["active"] = True
    workflows = [wf7]
    workflows.extend(
        {"name": name, "active": True, "nodes": []}
        for name in EXPECTED_ACTIVE_WORKFLOWS
        if name != "WF7_Career_Agent_Orchestrator"
    )

    checks = inspect_live_n8n_workflows(workflows)

    assert checks == [
        ("PASS", "Live n8n workflow activation", "5 expected workflows active"),
        ("PASS", "Live WF7 protected parameters", "Pipeline body and Discord summary match the repo"),
    ]


def test_live_n8n_inspection_detects_a_protected_wf7_mismatch() -> None:
    wf7 = json.loads(
        (ROOT_DIR / "n8n" / "workflows" / "WF7_Career_Agent_Orchestrator.json").read_text(encoding="utf-8")
    )
    wf7["active"] = True
    pipeline = next(node for node in wf7["nodes"] if node["name"] == "Run Career Agent Pipeline")
    pipeline["parameters"]["jsonBody"] = "changed"
    workflows = [wf7]
    workflows.extend(
        {"name": name, "active": True, "nodes": []}
        for name in EXPECTED_ACTIVE_WORKFLOWS
        if name != "WF7_Career_Agent_Orchestrator"
    )

    checks = inspect_live_n8n_workflows(workflows)

    assert checks[1][0] == "FAIL"
    assert "Run Career Agent Pipeline.jsonBody" in checks[1][2]


def test_apps_script_url_extraction_is_scoped_to_workflow_nodes() -> None:
    active_url = "https://script.google.com/macros/s/active-id/exec"
    workflow = {
        "nodes": [
            {"parameters": {"url": active_url}},
            {"parameters": {"jsonBody": {"callback": active_url}}},
        ],
        "ignored": "https://script.google.com/macros/s/not-a-node/exec",
    }

    assert extract_apps_script_urls(workflow) == {active_url}


def test_apps_script_endpoint_check_uses_cache_buster_and_hides_url(monkeypatch) -> None:
    url = "https://script.google.com/macros/s/sensitive-deployment-id/exec"
    seen_urls: list[str] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "success": True,
                    "script_version": "v16",
                    "status_options": expected_status_values(),
                }
            ).encode("utf-8")

    def fake_urlopen(probe_url: str, timeout: int):
        seen_urls.append(probe_url)
        assert timeout == 15
        return Response()

    monkeypatch.setattr("scripts.check_production_readiness.urllib.request.urlopen", fake_urlopen)

    check = check_apps_script_endpoint(
        f"Live n8n Apps Script {endpoint_fingerprint(url)}",
        url,
        "v16",
        expected_status_values(),
        "WF4_Gmail_Status_Monitor",
    )

    assert check[0] == "PASS"
    assert "sensitive-deployment-id" not in " ".join(check)
    assert "readiness=" in seen_urls[0]


def test_apps_script_endpoint_check_rejects_an_old_version(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {"success": True, "script_version": "v15", "status_options": expected_status_values()}
            ).encode("utf-8")

    monkeypatch.setattr(
        "scripts.check_production_readiness.urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(),
    )

    check = check_apps_script_endpoint(
        "Live n8n Apps Script redacted",
        "https://script.google.com/macros/s/sensitive-deployment-id/exec",
        "v16",
        expected_status_values(),
        "WF5_Email_Backfill_Scanner",
    )

    assert check[0] == "FAIL"
    assert "serves v15, expected v16 or newer" in check[2]


def test_command_error_handles_timeout_bytes() -> None:
    result = subprocess.CompletedProcess(["docker", "ps"], 124, b"", b"timed out\r\ncleanly")

    assert command_error(result) == "timed out cleanly"
