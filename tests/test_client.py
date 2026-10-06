import httpx
import pytest

from seeder.client.http import ApiError, SunbirdClient
from seeder.config import Settings

ENV = {"base_url": "https://sb.test", "retries": 2, "extra_headers": {},
       "keycloak": {"url": "https://sb.test/auth", "realm": "sunbird",
                    "admin_client_id": "lms", "user_client_id": "android"},
       "endpoints": {"content_read": "GET /api/content/v1/read/{id}",
                     "refresh_token": "POST /auth/v1/refresh/token"}}
SECRETS = {"SUNBIRD_API_KEY": "k", "ADMIN_USERNAME": "a", "ADMIN_PASSWORD": "p"}


def make_client(handler):
    return SunbirdClient(Settings(env=ENV, volumes={"run_id": "t"}, secrets=SECRETS),
                         transport=httpx.MockTransport(handler))


def fake_auth(req):
    if req.url.path.endswith("/openid-connect/token"):
        return httpx.Response(200, json={"access_token": "kc", "refresh_token": "r",
                                         "expires_in": 300})
    if req.url.path == "/auth/v1/refresh/token":
        return httpx.Response(200, json={"result": {"access_token": "t"}})
    return None


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None
    monkeypatch.setattr("seeder.client.http.asyncio.sleep", instant)


async def test_retries_then_succeeds():
    calls = {"read": 0}

    def handler(req):
        if (auth := fake_auth(req)) is not None:
            return auth
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
        if (auth := fake_auth(req)) is not None:
            return auth
        calls["read"] += 1
        return httpx.Response(400, text="bad request")

    c = make_client(handler)
    with pytest.raises(ApiError) as exc:
        await c.call("content_read", id="x")
    assert exc.value.status == 400 and calls["read"] == 1
    await c.close()


async def test_admin_login_exchanges_refresh_token():
    seen = []

    def handler(req):
        seen.append((req.url.path, req.headers.get("Authorization"),
                     dict(httpx.QueryParams(req.content.decode()))))
        if req.url.path.endswith("/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "kc", "refresh_token": "r1",
                                             "expires_in": 300})
        if req.url.path == "/auth/v1/refresh/token":
            return httpx.Response(200, json={"result": {"access_token": "api-tok"}})
        return httpx.Response(404)

    c = make_client(handler)
    assert await c.auth.admin_token() == "api-tok"
    (kc_path, kc_auth, kc_form), (rf_path, rf_auth, rf_form) = seen
    assert kc_path == "/auth/realms/sunbird/protocol/openid-connect/token"
    assert kc_form == {"client_id": "lms", "grant_type": "password",
                       "username": "a", "password": "p"}
    assert rf_path == "/auth/v1/refresh/token" and rf_form == {"refresh_token": "r1"}
    assert kc_auth == rf_auth == "Bearer k"
    await c.close()


async def test_local_mode_routes_to_services_without_api_key():
    seen = {}

    def handler(req):
        if (auth := fake_auth(req)) is not None:
            return auth
        seen[req.url.path] = (str(req.url), req.headers.get("Authorization"),
                              req.headers.get("x-authenticated-user-token"))
        return httpx.Response(200, json={"result": {}})

    env = dict(ENV, mode="local", local={
        "hosts": {"userorg": "http://userorg:9000", "content": "http://content:9000/"},
        "endpoints": {
            "user_create": {"route": "POST {userorg}/v1/user/create", "user_token": True},
            "content_read": {"route": "GET {content}/content/v3/read/{id}"}}})
    c = SunbirdClient(Settings(env=env, volumes={"run_id": "t"}, secrets=SECRETS),
                      transport=httpx.MockTransport(handler))
    await c.call("user_create", json={})
    await c.call("content_read", id="do_1")
    assert seen["/v1/user/create"] == ("http://userorg:9000/v1/user/create", None, "t")
    assert seen["/content/v3/read/do_1"] == ("http://content:9000/content/v3/read/do_1",
                                             None, None)
    await c.close()
