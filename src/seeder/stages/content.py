"""Content lifecycle: created -> uploaded -> in_review -> publish_requested -> live."""
from seeder import plan
from seeder.api import content as api
from seeder.stages.context import Ctx
from seeder.stages.runner import poll_until, run_all

KIND = "content"


async def seed(ctx: Ctx) -> int:
    store, c = ctx.store, ctx.client
    keys = [plan.content_key(ctx.run_id, i) for i in range(1, ctx.vol["contents"] + 1)]
    todo = [k for k in keys if store.status(KIND, k) not in ("publish_requested", "live")]

    async def advance(key: str) -> None:
        status = store.status(KIND, key)
        if status is None:
            cid = await api.create(c, key)
            store.upsert(KIND, key, "created", remote_id=cid)
            status = "created"
        cid = store.get(KIND, key)["remote_id"]
        if status == "created":
            url = await api.upload(c, cid)
            store.upsert(KIND, key, "uploaded", data={"artifact_url": url})
            status = "uploaded"
        if status == "uploaded":
            await api.review(c, cid)
            store.upsert(KIND, key, "in_review")
            status = "in_review"
        if status == "in_review":
            await api.publish(c, cid)
            store.upsert(KIND, key, "publish_requested")

    failed = await run_all("content", KIND, todo, advance, store, ctx.env["concurrency"])

    waiting = [r["key"] for r in store.list(KIND, "publish_requested")]

    async def is_live(key: str) -> bool:
        rec = store.get(KIND, key)
        if await api.status(c, rec["remote_id"]) == "Live":
            store.upsert(KIND, key, "live")
            return True
        return False

    poll = ctx.env["publish_poll"]
    stuck = await poll_until("content publish", KIND, waiting, is_live, store,
                             ctx.env["concurrency"], poll["interval_s"], poll["timeout_s"])
    return failed + len(stuck)
