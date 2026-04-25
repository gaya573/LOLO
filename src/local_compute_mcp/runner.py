from __future__ import annotations

import csv
import hashlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Worker


@dataclass(frozen=True)
class Job:
    job_id: str
    input: str


@dataclass
class JobResult:
    job_id: str
    worker: str
    input: str
    command: str
    status: str
    exit_code: int
    duration_sec: float
    stdout: str
    stderr: str


def test_worker(worker: Worker) -> JobResult:
    if worker.type == "local":
        command = "echo local-ok"
    else:
        command = "echo ssh-ok"
    return _run_on_worker(worker, command, "test", "test")


def discover_jobs(input_dir: str | Path, pattern: str) -> list[Job]:
    base = Path(input_dir)
    files = sorted(p for p in base.glob(pattern) if p.is_file())
    return [Job(job_id=_job_id(str(path)), input=str(path)) for path in files]


def run_jobs(
    workers: list[Worker],
    jobs: list[Job],
    command_template: str,
    output_dir: str | Path,
    logs_dir: str | Path,
) -> dict[str, object]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(logs_dir).mkdir(parents=True, exist_ok=True)

    slots: list[Worker] = []
    for worker in workers:
        slots.extend([worker] * max(1, worker.max_jobs))
    if not slots:
        raise ValueError("No enabled workers are configured.")

    results: list[JobResult] = []
    with ThreadPoolExecutor(max_workers=len(slots)) as executor:
        futures = []
        for index, job in enumerate(jobs):
            worker = slots[index % len(slots)]
            command = render_command(command_template, job, worker, output_dir)
            futures.append(executor.submit(_run_on_worker, worker, command, job.job_id, job.input))
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item.job_id)
    write_joblog(Path(logs_dir) / "joblog.tsv", results)
    return summarize(results)


def retry_failed(
    workers: list[Worker],
    command_template: str,
    output_dir: str | Path,
    logs_dir: str | Path,
) -> dict[str, object]:
    failed = read_failed_jobs(Path(logs_dir) / "joblog.tsv")
    jobs = [Job(job_id=row["job_id"], input=row["input"]) for row in failed]
    return run_jobs(workers, jobs, command_template, output_dir, logs_dir)


def render_command(command_template: str, job: Job, worker: Worker, output_dir: str | Path) -> str:
    input_path = Path(job.input)
    values = {
        "input": job.input,
        "input_q": _quote(str(job.input)),
        "input_name": input_path.name,
        "input_stem": input_path.stem,
        "output_dir": str(output_dir),
        "output_dir_q": _quote(str(output_dir)),
        "job_id": job.job_id,
        "worker": worker.name,
    }
    return command_template.format(**values)


def write_joblog(path: Path, results: list[JobResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()) if results else _joblog_fields(), delimiter="\t")
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def read_failed_jobs(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [row for row in reader if row.get("status") != "success"]


def summarize(results: list[JobResult]) -> dict[str, object]:
    total = len(results)
    failed = [item for item in results if item.status != "success"]
    return {
        "total": total,
        "success": total - len(failed),
        "failed": len(failed),
        "failed_jobs": [{"job_id": item.job_id, "input": item.input, "worker": item.worker, "exit_code": item.exit_code} for item in failed],
    }


def _run_on_worker(worker: Worker, command: str, job_id: str, input_path: str) -> JobResult:
    started = time.perf_counter()
    cwd: str | None = None
    shell = False
    if worker.type == "local":
        argv: str | list[str] = command
        cwd = str(Path(worker.workdir).resolve())
        shell = True
    elif worker.type == "ssh":
        argv = _ssh_command(worker, command)
    else:
        raise ValueError(f"Unsupported worker type: {worker.type}")

    completed = subprocess.run(argv, cwd=cwd, shell=shell, capture_output=True, text=True, encoding="utf-8", errors="replace")
    duration = time.perf_counter() - started
    return JobResult(
        job_id=job_id,
        worker=worker.name,
        input=input_path,
        command=command,
        status="success" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        duration_sec=round(duration, 3),
        stdout=completed.stdout[-4000:],
        stderr=completed.stderr[-4000:],
    )


def _ssh_command(worker: Worker, command: str) -> list[str]:
    remote_command = f'cd "{worker.workdir}" && {command}'
    argv = ["ssh", "-p", str(worker.port)]
    for option in worker.ssh_options:
        argv.extend(["-o", option])
    argv.extend([worker.target, remote_command])
    return argv


def _job_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def _joblog_fields() -> list[str]:
    return ["job_id", "worker", "input", "command", "status", "exit_code", "duration_sec", "stdout", "stderr"]
