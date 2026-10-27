"""Content lifecycle (same steps as the shell scripts): created -> uploaded -> publish_requested -> live."""
import asyncio

from seeder import plan
from seeder.api import content as api
from seeder.client.http import ApiError
from seeder.stages.context import Ctx
from seeder.stages.runner import poll_until, run_all

KIND = "content"
PUBLISH_ATTEMPTS = 3


async def publish_with_retry(c, cid: str, delay: float) -> None:
    """Upload is processed asynchronously, so an early publish can fail; retry a few times."""
    for attempt in range(PUBLISH_ATTEMPTS):
        try:
            await api.publish(c, cid)
            return
        except ApiError:
            if attempt == PUBLISH_ATTEMPTS - 1:
                raise
            await asyncio.sleep(delay)


async def upload_or_recover(c, cid: str, mime_type: str) -> str:
    """A slow upload can time out on our side but still succeed on the server. The retry is then
    rejected with "Invalid version Key", so check whether the file is already attached."""
    try:
        return await api.upload(c, cid, mime_type)
    except ApiError as exc:
        if exc.status == 400 and "version key" in exc.body.lower():
            url = await api.artifact_url(c, cid)
            if url:
                return url
        raise


async def seed(ctx: Ctx) -> int:
    store, c = ctx.store, ctx.client
    keys = [plan.content_key(ctx.run_id, i) for i in range(1, ctx.vol["contents"] + 1)]
    todo = [k for k in keys if store.status(KIND, k) not in ("publish_requested", "live")]

    delay = ctx.env.get("step_delay_s", 1)
    mp4_ratio = ctx.vol.get("mp4_ratio", 0.3)
    mime = {k: plan.content_mime(ctx.run_id, i, mp4_ratio)
            for i, k in enumerate(keys, start=1)}

    async def advance(key: str) -> None:
        status = store.status(KIND, key)
        if status is None:
            cid = await api.create(c, key, mime[key])
            store.upsert(KIND, key, "created", remote_id=cid, data={"mime_type": mime[key]})
            status = "created"
            await asyncio.sleep(delay)
        cid = store.get(KIND, key)["remote_id"]
        if status == "created":
            url = await upload_or_recover(c, cid, mime[key])
            store.upsert(KIND, key, "uploaded", data={"artifact_url": url})
            status = "uploaded"
            # videos are processed asynchronously: wait longer before publishing
            await asyncio.sleep(delay * (2 if mime[key] == "video/mp4" else 1))
        if status == "uploaded":
            await publish_with_retry(c, cid, delay)
            store.upsert(KIND, key, "publish_requested")

    failed = await run_all("content", KIND, todo, advance, store, ctx.env["concurrency"])
    if failed:
        return failed

    waiting = [r["key"] for r in store.list(KIND, "publish_requested")]

    async def is_live(key: str) -> bool:
        rec = store.get(KIND, key)
        state = await api.status(c, rec["remote_id"])
        if state == "Live":
            store.upsert(KIND, key, "live")
            return True
        if state == "Failed":  # the publish job gave up; recorded as this item's error
            raise RuntimeError("publish failed on the server (status Failed)")
        return False

    poll = ctx.env["publish_poll"]
    stuck = await poll_until("content publish", KIND, waiting, is_live, store,
                             ctx.env["concurrency"], poll["interval_s"], poll["timeout_s"])
    return len(stuck)
