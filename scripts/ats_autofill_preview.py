from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ats_autofill_service import ATSAutofillService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview guarded ATS autofill mappings for an HTML page.")
    parser.add_argument("--apply-plan", required=True, help="Path to an apply_plan.json file.")
    parser.add_argument("--html-file", required=True, help="Path to a saved ATS page or fixture HTML file.")
    parser.add_argument("--source-url", default="", help="Optional source URL to include in the report.")
    parser.add_argument("--output-json", default="", help="Optional path to write the full autofill plan JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    apply_plan_path = Path(args.apply_plan)
    html_path = Path(args.html_file)

    apply_plan = json.loads(apply_plan_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    service = ATSAutofillService()
    plan = service.build_plan_from_html(html, apply_plan, source_url=args.source_url)
    payload = plan.model_dump(mode="json")

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "total_fields": plan.total_fields,
                "fillable_count": plan.fillable_count,
                "manual_count": plan.manual_count,
                "skipped_count": plan.skipped_count,
                "output_json": args.output_json,
            },
            indent=2,
        )
    )
    for match in plan.matches:
        if match.action in {"fill_text", "select_option", "choose_radio", "manual_upload", "manual_review"}:
            answer = match.target_option or match.answer_value
            print(
                f"[{match.action}] {match.field.label or match.field.name or match.field.field_id}"
                f" -> {match.answer_key or 'manual'}"
                f"{f' = {answer}' if answer else ''}"
                f" ({match.confidence:.2f})"
            )


if __name__ == "__main__":
    main()
