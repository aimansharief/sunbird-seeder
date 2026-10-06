"""Fetches fresh learner tokens. Run shortly before a load test; tokens expire."""
import time

from seeder.stages.context import Ctx
from seeder.stages.runner import run_all

KIND = "user"


async def refresh(ctx: Ctx, max_age_s: float | None = None) -> int:
    now = time.time()
    users = ctx.store.list(KIND, "created")
    todo = [u["key"] for u in users
            if max_age_s is None or now - u["data"].get("token_at", 0) > max_age_s]

    async def work(key: str) -> None:
        token, ttl = await ctx.client.auth.user_token(key)
        ctx.store.upsert(KIND, key, "created",
                         data={"token": token, "token_at": time.time(), "token_ttl": ttl})

    return await run_all("tokens", KIND, todo, work, ctx.store,
                         ctx.env.get("token_concurrency", 20))
