from pathlib import Path


SCRIPT_PATH = Path("google_cloud/Code.gs")


def test_jobs_applied_writer_preserves_the_canonical_eight_columns() -> None:
    code = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'const SCRIPT_VERSION = "v16";' in code
    assert "const JOB_COL_COUNT = 8;" in code
    assert "getApplicationDate(data),\n    company,\n    role," in code
    assert "data.salary || \"N/A\"" in code
    assert "data.job_posted_on || \"Unknown\"" in code
    assert "appliedUsing,\n    status,\n    data.link || \"\"" in code


def test_jobs_applied_writer_gates_applied_and_dedupes_before_writing() -> None:
    code = SCRIPT_PATH.read_text(encoding="utf-8")
    handler = code[code.index("function handleJobsApplied"):code.index("function handleStatusUpdate")]

    assert "data.human_confirmed_submission !== true" in handler
    assert handler.index("findExistingJobRow") < handler.index("findFirstReusableJobRow")
    assert 'mode: "duplicate_skipped"' in handler
