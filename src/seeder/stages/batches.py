import logging

from seeder import plan
from seeder.api import batches as api
from seeder.stages.context import Ctx
from seeder.stages.runner import run_all

KIND = "batch"
log = logging.getLogger(__name__)


async def seed(ctx: Ctx) -> int:
    store = ctx.store
    course_for = {}
    for i in range(1, ctx.vol["courses"] + 1):
        bkey = plan.batch_key(ctx.run_id, i)
        if store.status(KIND, bkey) == "created":
            continue
        course = store.get("course", plan.course_key(ctx.run_id, i))
        if not course or course["status"] != "live":
            log.warning("%s skipped: course not Live", bkey)
            continue
        course_for[bkey] = (i, course)

    async def work(bkey: str) -> None:
        i, course = course_for[bkey]
        batch_id = await api.create(ctx.client, bkey, course["remote_id"])
        store.upsert(KIND, bkey, "created", remote_id=batch_id,
                     data={"course_index": i, "course_id": course["remote_id"]})

    return await run_all("batches", KIND, list(course_for), work, store,
                         ctx.env["concurrency"])
