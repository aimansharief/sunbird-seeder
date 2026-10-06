from pathlib import Path

from seeder.client.http import SunbirdClient
from seeder.payloads import builders as b

ASSET = Path("assets/test.pdf")


async def create(c: SunbirdClient, key: str) -> str:
    res = await c.call("content_create",
                       json=b.content_create(key, c.s.env, c.s.creator_id), role="creator")
    return res["result"]["identifier"]


async def upload(c: SunbirdClient, content_id: str) -> str:
    data = ASSET.read_bytes()
    res = await c.call("content_upload", id=content_id,
                       files={"file": (ASSET.name, data, "application/pdf")}, role="creator")
    return res.get("result", {}).get("content_url", "")


async def review(c: SunbirdClient, content_id: str) -> None:
    await c.call("content_review", id=content_id, json=b.review(), role="creator")


async def publish(c: SunbirdClient, content_id: str) -> None:
    await c.call("content_publish", id=content_id,
                 json=b.publish(c.s.reviewer_id), role="reviewer")


async def status(c: SunbirdClient, content_id: str) -> str:
    res = await c.call("content_read", id=content_id, params={"fields": "status"})
    return res["result"]["content"]["status"]
