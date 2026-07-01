from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.dependencies import get_application_orchestrator_service
from app.schemas.queue import QueueProcessNextRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Process queued CareerSite job leads.")
    parser.add_argument("--worker-id", default="local-worker", help="Worker name recorded in queue leases.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum queued jobs to process.")
    parser.add_argument("--lease-seconds", type=int, default=900, help="Queue claim lease in seconds.")
    parser.add_argument("--output-root", default="data/outputs/queue_packets", help="Packet output root.")
    parser.add_argument("--render-pdf", action="store_true", help="Render tailored resume PDFs.")
    parser.add_argument("--no-export-packet", action="store_true", help="Only score/process jobs; do not export packets.")
    args = parser.parse_args()

    response = get_application_orchestrator_service().process_next(
        QueueProcessNextRequest(
            worker_id=args.worker_id,
            limit=args.limit,
            lease_seconds=args.lease_seconds,
            export_packet=not args.no_export_packet,
            render_pdf=args.render_pdf,
            output_root_override=args.output_root,
        )
    )

    print(json.dumps(response.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
