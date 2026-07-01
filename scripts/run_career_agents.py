from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.dependencies import get_career_agent_orchestrator_service
from app.schemas.agent import (
    CareerPipelineAgentRequest,
    JobDiscoveryAgentRequest,
    PageWatcherAgentRequest,
    ResumeTailoringAgentRequest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local CareerSite AI agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Run the Job Discovery Agent.")
    discover.add_argument("--max-companies", type=int, default=8)
    discover.add_argument("--max-jobs-per-company", type=int, default=8)
    discover.add_argument("--no-refresh", action="store_true")
    discover.add_argument("--no-enqueue", action="store_true")
    discover.add_argument("--use-llm", action="store_true")
    discover.add_argument("--min-match-score", type=int, default=70)

    pipeline = sub.add_parser("pipeline", help="Run discovery plus queue processing.")
    pipeline.add_argument("--max-companies", type=int, default=8)
    pipeline.add_argument("--max-jobs-per-company", type=int, default=8)
    pipeline.add_argument("--process-limit", type=int, default=5)
    pipeline.add_argument("--render-pdf", action="store_true")
    pipeline.add_argument("--output-root", default="data/outputs/agent_packets")
    pipeline.add_argument("--use-llm", action="store_true")

    tailor = sub.add_parser("tailor", help="Run Resume Tailoring Agent for a queue item.")
    tailor.add_argument("--queue-id", required=True)
    tailor.add_argument("--render-pdf", action="store_true")
    tailor.add_argument("--output-root", default="data/outputs/agent_packets")
    tailor.add_argument("--update-queue", action="store_true")

    observe = sub.add_parser("observe", help="Run the Page Watcher Agent on a job/application URL.")
    observe.add_argument("--url", required=True)
    observe.add_argument("--use-llm", action="store_true")

    args = parser.parse_args()
    service = get_career_agent_orchestrator_service()

    if args.command == "discover":
        result = service.discover_jobs(
            JobDiscoveryAgentRequest(
                max_companies=args.max_companies,
                max_jobs_per_company=args.max_jobs_per_company,
                refresh_live=not args.no_refresh,
                enqueue=not args.no_enqueue,
                use_llm=args.use_llm,
                min_match_score=args.min_match_score,
            )
        )
    elif args.command == "pipeline":
        result = service.run_pipeline(
            CareerPipelineAgentRequest(
                discover=JobDiscoveryAgentRequest(
                    max_companies=args.max_companies,
                    max_jobs_per_company=args.max_jobs_per_company,
                    use_llm=args.use_llm,
                    enqueue=True,
                ),
                process_limit=args.process_limit,
                render_pdf=args.render_pdf,
                output_root_override=args.output_root,
            )
        )
    elif args.command == "tailor":
        result = service.tailor_resume(
            ResumeTailoringAgentRequest(
                queue_id=args.queue_id,
                render_pdf=args.render_pdf,
                output_root_override=args.output_root,
                update_queue=args.update_queue,
            )
        )
    else:
        result = service.observe_page(
            PageWatcherAgentRequest(
                url=args.url,
                use_llm=args.use_llm,
                fetch_if_empty=True,
            )
        )

    print(json.dumps(result.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
