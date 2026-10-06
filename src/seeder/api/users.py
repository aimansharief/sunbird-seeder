from seeder.client.http import ApiError, SunbirdClient
from seeder.payloads import builders as b


async def create(c: SunbirdClient, key: str) -> str:
    body = b.user_create(key, c.s.env, c.s.secrets["TEST_USER_PASSWORD"])
    try:
        res = await c.call("user_create", json=body)
        return res["result"]["userId"]
    except ApiError as exc:
        # A previous run may have created the user before crashing.
        if exc.status == 400 and "exist" in exc.body.lower():
            found = await find_id(c, key)
            if found:
                return found
        raise


async def find_id(c: SunbirdClient, username: str) -> str | None:
    res = await c.call("user_search", json=b.user_search_by_username(username))
    items = res.get("result", {}).get("response", {}).get("content", [])
    return items[0].get("id") if items else None
