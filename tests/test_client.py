import httpx
import pytest

from seeder.client.http import ApiError, SunbirdClient
from seeder.config import Settings

ENV = {"base_url": "https://sb.test", "retries": 2, "extra_headers": {},
       "keycloak": {"url": "https://sb.test/auth", "realm": "sunbird",
                    "admin_client_id": "lms", "user_client_id": "android"},
       "endpoints": {"content_read": "GET /api/content/v1/read/{id}"}}
SECRETS = {"SUNBIRD_API_KEY": "k", "ADMIN_USERNAME": "a", "ADMIN_PASSWORD": "p"}


def make_client(handler):
    return SunbirdClient(Settings(env=ENV, volumes={"run_id": "t"}, secrets=SECRETS),
                         transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None
    monkeypatch.setattr("seeder.client.http.asyncio.sleep", instant)


async def test_retries_then_succeeds():
    calls = {"read": 0}

    def handler(req):
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        calls["read"] += 1
        assert req.headers["x-authenticated-user-token"] == "t"
        assert req.url.path == "/api/content/v1/read/do_1"
        if calls["read"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"result": {"content": {"status": "Live"}}})

    c = make_client(handler)
    res = await c.call("content_read", id="do_1")
    assert res["result"]["content"]["status"] == "Live" and calls["read"] == 3
    await c.close()


async def test_client_error_is_not_retried():
    calls = {"read": 0}

    def handler(req):
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        calls["read"] += 1
        return httpx.Response(400, text="bad request")

    c = make_client(handler)
    with pytest.raises(ApiError) as exc:
        await c.call("content_read", id="x")
    assert exc.value.status == 400 and calls["read"] == 1
    await c.close()
