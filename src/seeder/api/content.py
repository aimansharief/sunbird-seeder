from pathlib import Path

from seeder.client.http import SunbirdClient
from seeder.payloads import builders as b

ASSETS = {
    "application/pdf": Path("assets/test.pdf"),
    "video/mp4": Path("assets/test.mp4"),
}


async def create(c: SunbirdClient, key: str, mime_type: str) -> str:
    res = await c.call("content_create",
                       json=b.content_create(key, c.s.env, c.s.creator_id, mime_type),
                       role="creator")
    return res["result"]["identifier"]


async def upload(c: SunbirdClient, content_id: str, mime_type: str) -> str:
    asset = ASSETS[mime_type]
    res = await c.call("content_upload", id=content_id,
                       files={"file": (asset.name, asset.read_bytes(), mime_type)},
                       role="creator")
    return res.get("result", {}).get("content_url", "")


async def publish(c: SunbirdClient, content_id: str) -> None:
    await c.call("content_publish", id=content_id,
                 json=b.publish(c.s.reviewer_id), role="reviewer")


async def status(c: SunbirdClient, content_id: str) -> str:
    res = await c.call("content_read", id=content_id, params={"fields": "status"})
    return res["result"]["content"]["status"]
