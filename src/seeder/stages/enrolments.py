import logging
import time

from seeder import plan
from seeder.api import enrolments as api
from seeder.stages.context import Ctx
from seeder.stages.runner import run_all

KIND = "enrolment"
log = logging.getLogger(__name__)


async def seed(ctx: Ctx) -> int:
    store, run, vol = ctx.store, ctx.run_id, ctx.vol
    as_user = ctx.env.get("enrol_as", "user") == "user"
    jobs: dict[str, tuple[str, int, dict]] = {}

    for b in store.list("batch", "created"):
        ci = b["data"]["course_index"]
        for ui in plan.batch_user_indices(ci, vol["users_per_batch"], vol["users"]):
            ekey = plan.enrol_key(run, ci, ui)
            if store.status(KIND, ekey) == "enrolled":
                continue
            ukey = plan.user_key(run, ui)
            if store.status("user", ukey) != "created":
                continue
            jobs[ekey] = (ukey, ui, b)

    async def work(ekey: str) -> None:
        ukey, ui, b = jobs[ekey]
        user = store.get("user", ukey)
        token = None
        if as_user:
            data = user["data"]
            fresh = time.time() - data.get("token_at", 0) < data.get("token_ttl", 0) - 60
            if fresh:
                token = data["token"]
            else:
                token, ttl = await ctx.client.auth.user_token(ukey)
                store.upsert("user", ukey, "created",
                             data={"token": token, "token_at": time.time(), "token_ttl": ttl})
        await api.enrol(ctx.client, user["remote_id"], b["data"]["course_id"],
                        b["remote_id"], user_token=token)
        store.upsert(KIND, ekey, "enrolled", data={
            "user_key": ukey, "user_index": ui, "user_id": user["remote_id"],
            "course_id": b["data"]["course_id"], "batch_id": b["remote_id"],
            "course_index": b["data"]["course_index"]})

    return await run_all("enrolments", KIND, list(jobs), work, store,
                         ctx.env["concurrency"])
