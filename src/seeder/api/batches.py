from seeder.client.http import SunbirdClient
from seeder.payloads import builders as b


async def create(c: SunbirdClient, key: str, course_id: str) -> str:
    res = await c.call("batch_create",
                       json=b.batch_create(key, course_id, c.s.env, c.s.creator_id),
                       role="creator")
    result = res["result"]
    return result.get("batchId") or result.get("response")
