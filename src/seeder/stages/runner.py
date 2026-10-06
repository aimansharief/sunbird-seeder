"""Runs a worker over many keys with bounded concurrency and progress logs."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from seeder.state.store import Store

log = logging.getLogger(__name__)


async def run_all(label: str, kind: str, keys: list[str],
                  worker: Callable[[str], Awaitable[None]],
                  store: Store, concurrency: int) -> int:
    """Returns the number of failed keys. Failures are recorded in the store."""
    total = len(keys)
    if total == 0:
        log.info("%s: nothing to do", label)
        return 0
    sem = asyncio.Semaphore(concurrency)
    done = failed = 0
    step = max(1, total // 20)
    started = time.monotonic()

    async def one(key: str) -> None:
        nonlocal done, failed
        async with sem:
            try:
                await worker(key)
            except Exception as exc:  # noqa: BLE001 - record and continue
                failed += 1
                store.mark_error(kind, key, f"{type(exc).__name__}: {exc}")
                log.debug("%s failed %s: %s", label, key, exc)
            finally:
                done += 1
                if done % step == 0 or done == total:
                    rate = done / max(time.monotonic() - started, 1e-6)
                    log.info("%s: %d/%d done, %d failed (%.1f/s)",
                             label, done, total, failed, rate)

    await asyncio.gather(*(one(k) for k in keys))
    return failed


async def poll_until(label: str, kind: str, keys: list[str],
                     check: Callable[[str], Awaitable[bool]],
                     store: Store, concurrency: int,
                     interval_s: float, timeout_s: float) -> list[str]:
    """Checks keys in rounds until check() is True for all or timeout. Returns unfinished keys."""
    pending = list(keys)
    deadline = time.monotonic() + timeout_s
    while pending and time.monotonic() < deadline:
        finished: list[str] = []

        async def probe(key: str) -> None:
            if await check(key):
                finished.append(key)

        await run_all(f"{label} poll", kind, pending, probe, store, concurrency)
        done_set = set(finished)
        pending = [k for k in pending if k not in done_set]
        log.info("%s: %d still waiting", label, len(pending))
        if pending:
            await asyncio.sleep(interval_s)
    for key in pending:
        store.mark_error(kind, key, f"{label}: timed out waiting")
    return pending
