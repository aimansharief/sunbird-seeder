"""Prints progress by entity and status, plus recent errors."""
from __future__ import annotations

from seeder.state.store import Store

EXPECTED_DONE = {"user": "created", "content": "live", "course": "live",
                 "batch": "created", "enrolment": "enrolled"}


def expected_counts(vol: dict) -> dict:
    return {"user": vol["users"], "content": vol["contents"], "course": vol["courses"],
            "batch": vol["courses"], "enrolment": vol["courses"] * vol["users_per_batch"]}


def report(store: Store, vol: dict, show_errors: int = 10) -> bool:
    expected = expected_counts(vol)
    done = {k: 0 for k in expected}
    print(f"{'kind':<10} {'status':<20} {'count':>8} {'with error':>11}")
    for kind, status, count, errs in store.counts():
        print(f"{kind:<10} {str(status):<20} {count:>8} {errs or 0:>11}")
        if EXPECTED_DONE.get(kind) == status:
            done[kind] = count
    print()
    ok = True
    for kind, want in expected.items():
        mark = "OK " if done[kind] == want else "GAP"
        ok &= done[kind] == want
        print(f"{mark} {kind:<10} done {done[kind]:>6} / expected {want}")
    errors = store.errors(show_errors)
    if errors:
        print(f"\nRecent errors (latest {len(errors)}):")
        for e in errors:
            print(f"  {e['kind']} {e['key']} [{e['status']}] {e['error'][:200]}")
    return ok
