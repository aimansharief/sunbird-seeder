from seeder.client.http import ApiError, SunbirdClient
from seeder.payloads import builders as b


async def enrol(c: SunbirdClient, user_id: str, course_id: str, batch_id: str,
                user_token: str) -> None:
    try:
        await c.call("enrol", json=b.enrol(user_id, course_id, batch_id),
                     user_token=user_token)
    except ApiError as exc:
        # Already enrolled from an earlier run counts as success.
        if exc.status == 400 and "already" in exc.body.lower():
            return
        raise
