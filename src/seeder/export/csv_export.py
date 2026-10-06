"""Writes JMeter CSVs from the store. Per-user files are split per JMeter worker."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from seeder import plan
from seeder.export.distribution import weighted_rows
from seeder.state.store import Store

log = logging.getLogger(__name__)


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    log.info("wrote %s (%d rows)", path, len(rows))


def export_all(store: Store, volumes: dict, out_dir: Path, workers: int) -> Path:
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    cfg = volumes.get("export", {})
    rows, skew, seed = cfg.get("read_rows", 20000), cfg.get("skew", 1.0), cfg.get("seed", 42)

    content_ids = [r["remote_id"] for r in store.list("content", "live")]
    _write(csv_dir / "content.csv", ["contentId"],
           [[i] for i in weighted_rows(content_ids, rows, skew, seed)])

    courses = store.list("course", "live")
    _write(csv_dir / "courses.csv", ["courseId"],
           [[i] for i in weighted_rows([c["remote_id"] for c in courses], rows, skew, seed + 1)])
    course_contents = {c["remote_id"]: c["data"].get("content_ids", []) for c in courses}

    users = store.list("user", "created")
    users_by_worker: dict[int, list[list]] = {w: [] for w in range(1, workers + 1)}
    for n, u in enumerate(users, start=1):
        users_by_worker[plan.worker_for_user(n, workers)].append(
            [u["remote_id"], u["key"], u["data"].get("token", "")])

    user_worker = {u["key"]: plan.worker_for_user(n, workers)
                   for n, u in enumerate(users, start=1)}
    tokens = {u["key"]: u["data"].get("token", "") for u in users}
    enrol_by_worker: dict[int, list[list]] = {w: [] for w in range(1, workers + 1)}
    for e in store.list("enrolment", "enrolled"):
        d = e["data"]
        w = user_worker.get(d["user_key"])
        if w is None:
            continue
        enrol_by_worker[w].append([
            d["user_id"], d["course_id"], d["batch_id"],
            "|".join(course_contents.get(d["course_id"], [])), tokens.get(d["user_key"], "")])

    for w in range(1, workers + 1):
        _write(csv_dir / f"users_worker{w}.csv",
               ["userId", "userName", "accessToken"], users_by_worker[w])
        _write(csv_dir / f"enrolments_worker{w}.csv",
               ["userId", "courseId", "batchId", "contentIds", "accessToken"],
               enrol_by_worker[w])

    if not any(tokens.values()):
        log.warning("no user tokens in store; run `seeder tokens` then export again")
    return csv_dir
