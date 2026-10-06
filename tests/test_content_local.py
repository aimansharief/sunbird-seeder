"""Content stage in local mode against a fake knowlg v4: create -> upload -> publish -> Live."""
import json
import os
import shutil

import httpx
import yaml

from seeder.client.http import SunbirdClient
from seeder.config import Settings
from seeder.stages import content
from seeder.stages.context import Ctx
from seeder.state.store import Store

ROOT = os.path.join(os.path.dirname(__file__), "..")


class FakeKnowlg:
    def __init__(self):
        self.n = 0
        self.status, self.mime, self.requests = {}, {}, []
        self.publish_failures = 1          # first publish fails, retry must recover

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        self.requests.append((req.method, str(req.url), dict(req.headers)))
        ok = lambda result: httpx.Response(200, json={"result": result})
        if p == "/content/v4/create":
            body = json.loads(req.content)["request"]["content"]
            assert "contentType" not in body and body["primaryCategory"] == "Learning Resource"
            assert body["creator"] == "creator1" and body["createdBy"] == "creator-id" and body["framework"] == "fw-1" and body["channel"] == "chan-1"
            self.n += 1
            ident = f"do_{self.n}"
            self.status[ident], self.mime[ident] = "Draft", body["mimeType"]
            return ok({"identifier": ident})
        if p.startswith("/content/v4/upload/"):
            assert b"filename=" in req.content
            return ok({"content_url": "https://cdn/x"})
        if p.startswith("/content/v4/publish/"):
            if self.publish_failures:
                self.publish_failures -= 1
                return httpx.Response(400, json={"params": {"err": "ERR_CONTENT_PUBLISH"}})
            assert json.loads(req.content)["request"]["content"]["lastPublishedBy"] == "reviewer-id"
            self.status[p.rsplit("/", 1)[1]] = "Live"
            return ok({"publishStatus": "pushed"})
        if p.startswith("/content/v4/read/"):
            return ok({"content": {"status": self.status[p.rsplit("/", 1)[1]]}})
        return httpx.Response(404, text=p)


async def test_content_local_v4(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("assets")
    for name in ("test.pdf", "test.mp4"):
        shutil.copy(os.path.join(ROOT, "assets", name), f"assets/{name}")

    with open(os.path.join(ROOT, "config", "bench.yaml")) as f:
        env = yaml.safe_load(f)
    env.update(mode="local", output_root=str(tmp_path), retries=0, step_delay_s=0,
               channel="chan-1", framework="fw-1", extra_headers={"X-Channel-Id": "chan-1"})
    env["local"]["hosts"]["knowlg"] = "http://knowlg.test"
    env["publish_poll"] = {"interval_s": 0, "timeout_s": 5}
    vol = {"run_id": "t1", "contents": 12, "mp4_ratio": 0.5}
    settings = Settings(env=env, volumes=vol, secrets={"CONTENT_CREATOR_USERNAME": "creator1", "CONTENT_CREATOR_ID": "creator-id",
                     "CONTENT_REVIEWER_USERNAME": "reviewer1", "CONTENT_REVIEWER_ID": "reviewer-id"})
    fake = FakeKnowlg()
    store = Store(settings.output_dir / "state.db")
    client = SunbirdClient(settings, transport=httpx.MockTransport(fake))
    ctx = Ctx(settings, store, client)

    assert await content.seed(ctx) == 0
    assert [r["status"] for r in store.list("content")] == ["live"] * 12
    assert set(fake.mime.values()) == {"application/pdf", "video/mp4"}
    # local calls go straight to the service: no API key, no user token, no review call
    assert all("authorization" not in h and "x-authenticated-user-token" not in h
               for _, _, h in fake.requests)
    assert all("/review/" not in url for _, url, _ in fake.requests)
    assert all(h["x-channel-id"] == "chan-1" for _, _, h in fake.requests)
    await client.close()
