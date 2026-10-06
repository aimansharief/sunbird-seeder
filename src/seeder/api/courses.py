import uuid

from seeder.client.http import SunbirdClient
from seeder.payloads import builders as b


async def create(c: SunbirdClient, key: str) -> str:
    res = await c.call("course_create",
                       json=b.course_create(key, c.s.env, c.s.creator_id, c.s.creator_name),
                       role="creator")
    return res["result"]["identifier"]


async def update_hierarchy(c: SunbirdClient, course_id: str, course_name: str,
                           units: list[list[str]]) -> None:
    """Two updates. The first creates the units under temporary IDs; the server swaps in real
    IDs but stores relational_metadata under the temporary ones, which fails publish
    ("key not found: <unit id>"). The second re-sends the tree keyed by the real unit IDs."""
    temp_ids = [str(uuid.uuid4()) for _ in units]
    first = await c.call("course_hierarchy", role="creator", json=b.course_hierarchy(
        course_id, course_name, units, c.s.creator_id, temp_ids, new=True))
    real = first["result"]["identifiers"]
    unit_ids = [real[t] for t in temp_ids]
    await c.call("course_hierarchy", role="creator", json=b.course_hierarchy(
        course_id, course_name, units, c.s.creator_id, unit_ids, new=False))


async def publish(c: SunbirdClient, course_id: str) -> None:
    await c.call("course_publish", id=course_id,
                 json=b.publish(c.s.reviewer_id), role="reviewer")


async def status(c: SunbirdClient, course_id: str) -> str:
    res = await c.call("course_read", id=course_id, params={"fields": "status"})
    return res["result"]["content"]["status"]
