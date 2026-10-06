"""Course lifecycle: created -> hierarchy_updated -> in_review -> publish_requested -> live."""
import logging

from seeder import plan
from seeder.api import courses as api
from seeder.stages.context import Ctx
from seeder.stages.runner import poll_until, run_all

KIND = "course"
log = logging.getLogger(__name__)


def child_content_ids(ctx: Ctx, course_i: int) -> list[str] | None:
    """Live content IDs for a course, or None if any child is not Live yet."""
    idxs = plan.course_content_indices(course_i, ctx.vol["contents_per_course"],
                                       ctx.vol["contents"])
    ids = []
    for i in idxs:
        rec = ctx.store.get("content", plan.content_key(ctx.run_id, i))
        if not rec or rec["status"] != "live":
            return None
        ids.append(rec["remote_id"])
    return ids


async def seed(ctx: Ctx) -> int:
    store, c = ctx.store, ctx.client
    index = {plan.course_key(ctx.run_id, i): i for i in range(1, ctx.vol["courses"] + 1)}
    todo = []
    for key, i in index.items():
        if store.status(KIND, key) in ("publish_requested", "live"):
            continue
        if child_content_ids(ctx, i) is None:
            log.warning("%s skipped: child content not all Live", key)
            continue
        todo.append(key)

    async def advance(key: str) -> None:
        children = child_content_ids(ctx, index[key])
        status = store.status(KIND, key)
        if status is None:
            cid = await api.create(c, key)
            store.upsert(KIND, key, "created", remote_id=cid,
                         data={"content_ids": children})
            status = "created"
        cid = store.get(KIND, key)["remote_id"]
        if status == "created":
            units = plan.split_units(children, ctx.vol["units_per_course"])
            await api.update_hierarchy(c, cid, units)
            store.upsert(KIND, key, "hierarchy_updated")
            status = "hierarchy_updated"
        if status == "hierarchy_updated":
            await api.review(c, cid)
            store.upsert(KIND, key, "in_review")
            status = "in_review"
        if status == "in_review":
            await api.publish(c, cid)
            store.upsert(KIND, key, "publish_requested")

    failed = await run_all("courses", KIND, todo, advance, store, ctx.env["concurrency"])

    waiting = [r["key"] for r in store.list(KIND, "publish_requested")]

    async def is_live(key: str) -> bool:
        if await api.status(c, store.get(KIND, key)["remote_id"]) == "Live":
            store.upsert(KIND, key, "live")
            return True
        return False

    poll = ctx.env["publish_poll"]
    stuck = await poll_until("course publish", KIND, waiting, is_live, store,
                             ctx.env["concurrency"], poll["interval_s"], poll["timeout_s"])
    return failed + len(stuck)
