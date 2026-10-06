from seeder import plan
from seeder.api import users as api
from seeder.stages.context import Ctx
from seeder.stages.runner import run_all

KIND = "user"


async def seed(ctx: Ctx) -> int:
    index = {plan.user_key(ctx.run_id, i): i for i in range(1, ctx.vol["users"] + 1)}
    todo = [k for k in index if ctx.store.status(KIND, k) != "created"]

    async def work(key: str) -> None:
        user_id = await api.create(ctx.client, key, index[key])
        ctx.store.upsert(KIND, key, "created", remote_id=user_id,
                         data={"username": key})

    return await run_all("users", KIND, todo, work, ctx.store, ctx.env["concurrency"])
