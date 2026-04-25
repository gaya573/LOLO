from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_workers
from .runner import discover_jobs, retry_failed, run_jobs, test_worker


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Compute MCP CLI")
    parser.add_argument("--config", default="workers.yaml")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparsers.add_parser("test")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--pattern", default="*")
    run_parser.add_argument("--command", required=True)
    run_parser.add_argument("--output", default="outputs")
    run_parser.add_argument("--logs", default="logs")

    retry_parser = subparsers.add_parser("retry")
    retry_parser.add_argument("--command", required=True)
    retry_parser.add_argument("--output", default="outputs")
    retry_parser.add_argument("--logs", default="logs")

    args = parser.parse_args()
    workers = load_workers(args.config)

    if args.cmd == "test":
        results = [test_worker(worker).__dict__ for worker in workers]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(item["status"] == "success" for item in results) else 1

    if args.cmd == "run":
        jobs = discover_jobs(args.input, args.pattern)
        summary = run_jobs(workers, jobs, args.command, Path(args.output), Path(args.logs))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["failed"] == 0 else 1

    if args.cmd == "retry":
        summary = retry_failed(workers, args.command, Path(args.output), Path(args.logs))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["failed"] == 0 else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
