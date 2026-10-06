"""Retires seeded content and courses. Users, batches and enrolments are not deleted."""
from __future__ import annotations

from seeder.stages.context import Ctx
from seeder.stages.runner import run_all


async def retire(ctx: Ctx) -> int:
    failed = 0
    for kind, endpoint in (("course", "course_retire"), ("content", "content_retire")):
        recs = {r["key"]: r for r in ctx.store.list(kind) if r["remote_id"]
                and r["status"] != "retired"}

        async def work(key: str, kind=kind, endpoint=endpoint, recs=recs) -> None:
            await ctx.client.call(endpoint, id=recs[key]["remote_id"])
            ctx.store.upsert(kind, key, "retired")

        failed += await run_all(f"retire {kind}", kind, list(recs), work,
                                ctx.store, ctx.env["concurrency"])
    return failed
