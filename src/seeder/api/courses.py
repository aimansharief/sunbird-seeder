from seeder.client.http import SunbirdClient
from seeder.payloads import builders as b


async def create(c: SunbirdClient, key: str) -> str:
    res = await c.call("course_create",
                       json=b.course_create(key, c.s.env, c.s.creator_id), role="creator")
    return res["result"]["identifier"]


async def update_hierarchy(c: SunbirdClient, course_id: str,
                           units: list[list[str]]) -> None:
    await c.call("course_hierarchy", json=b.course_hierarchy(course_id, units),
                 role="creator")


async def review(c: SunbirdClient, course_id: str) -> None:
    await c.call("course_review", id=course_id, json=b.review(), role="creator")


async def publish(c: SunbirdClient, course_id: str) -> None:
    await c.call("course_publish", id=course_id,
                 json=b.publish(c.s.reviewer_id), role="reviewer")


async def status(c: SunbirdClient, course_id: str) -> str:
    res = await c.call("course_read", id=course_id, params={"fields": "status"})
    return res["result"]["content"]["status"]
