"""Runs every stage and export against an in-memory fake Sunbird."""
import csv
import itertools
import json

import httpx
import pytest
import yaml

from seeder.client.http import SunbirdClient
from seeder.config import Settings
from seeder.export.csv_export import export_all
from seeder.stages import batches, content, courses, enrolments, users
from seeder.stages.context import Ctx
from seeder.state.store import Store
from seeder.verify import report


class FakeSunbird:
    def __init__(self):
        self.ids = itertools.count(1)
        self.status = {}
        self.enrolled = set()
        self.flaky_once = True
        self.root_org = None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        ok = lambda result: httpx.Response(200, json={"result": result})
        if p.endswith("/openid-connect/token"):
            user = dict(httpx.QueryParams(req.content.decode()))["username"]
            return httpx.Response(200, json={"access_token": "kc-only",
                                             "refresh_token": f"r:{user}:{next(self.ids)}",
                                             "expires_in": 600})
        if p == "/auth/v1/refresh/token":
            rt = dict(httpx.QueryParams(req.content.decode()))["refresh_token"]
            return ok({"access_token": "tok" + rt[1:]})
        token = req.headers.get("x-authenticated-user-token", "")
        if token == "kc-only":
            return httpx.Response(401, text="keycloak token not accepted")
        who = token.split(":")[1] if token.startswith("tok:") else None
        if p.startswith("/api/user/"):
            assert who == "a"
        elif "/publish/" in p:
            assert who == "reviewer_login"
        elif p.startswith(("/api/content/", "/api/collection/")) and "/read/" not in p \
                or p == "/api/course/v1/batch/create":
            assert who == "creator_login", (p, who)
        if p == "/api/user/v1/create":
            r = json.loads(req.content)["request"]
            assert r["channel"] == "custodian" and r["roles"] == ["PUBLIC"]
            assert r["firstName"] == "User" and r["userName"] == f"user{r['lastName']}_t1"
            if self.flaky_once:          # exercise the retry path once
                self.flaky_once = False
                return httpx.Response(503)
            return ok({"userId": f"user-{next(self.ids)}"})
        if p in ("/api/content/v1/create", "/api/collection/v1/create"):
            assert json.loads(req.content)["request"]["content"]["createdBy"] == "creator"
            ident = f"do_{next(self.ids)}"
            self.status[ident] = "Draft"
            return ok({"identifier": ident})
        if "/upload/" in p:
            return ok({"content_url": "https://cdn/x.pdf"})
        if "/review/" in p:
            self.status[p.rsplit("/", 1)[1]] = "Review"
            return ok({})
        if "/publish/" in p:
            body = json.loads(req.content)["request"]["content"]
            assert body["lastPublishedBy"] == "reviewer"
            self.status[p.rsplit("/", 1)[1]] = "Live"
            return ok({})
        if "/read/" in p:
            return ok({"content": {"status": self.status[p.rsplit("/", 1)[1]]}})
        if p == "/api/collection/v1/hierarchy/update":
            return ok({})
        if p == "/api/course/v1/batch/create":
            r = json.loads(req.content)["request"]
            assert r["createdBy"] == "creator" and r["createdFor"] == [self.root_org]
            assert r["endDate"] is None and r["mentors"] == [] and r["tandc"] is True
            return ok({"batchId": f"batch-{next(self.ids)}"})
        if p == "/api/course/v1/enrol":
            r = json.loads(req.content)["request"]
            assert who and who.startswith("user") and who.endswith("_t1")   # learner's own token
            self.enrolled.add((r["userId"], r["batchId"]))
            return ok({"response": "SUCCESS"})
        return httpx.Response(404, text=p)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None
    monkeypatch.setattr("seeder.client.http.asyncio.sleep", instant)
    monkeypatch.setattr("seeder.stages.runner.asyncio.sleep", instant)


async def test_full_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)  # assets path is relative to repo root
    import os, shutil
    os.makedirs("assets", exist_ok=True)
    repo_asset = os.path.join(os.path.dirname(__file__), "..", "assets", "test.pdf")
    shutil.copy(repo_asset, "assets/test.pdf")
    shutil.copy(repo_asset.replace("test.pdf", "test.mp4"), "assets/test.mp4")

    with open(os.path.join(os.path.dirname(__file__), "..", "config", "bench.yaml")) as f:
        env = yaml.safe_load(f)
    env.update(base_url="https://sb.test", output_root=str(tmp_path), retries=2,
               custodian_channel="custodian", mode="public")
    env["publish_poll"] = {"interval_s": 0, "timeout_s": 5}
    vol = {"run_id": "t1", "users": 20, "contents": 12, "courses": 3,
           "contents_per_course": 4, "units_per_course": 2, "users_per_batch": 8}
    secrets = {"SUNBIRD_API_KEY": "k", "ADMIN_USERNAME": "a", "ADMIN_PASSWORD": "p",
               "ADMIN_USER_ID": "admin", "CONTENT_CREATOR_ID": "creator",
               "CONTENT_REVIEWER_ID": "reviewer",
               "CONTENT_CREATOR_USERNAME": "creator_login", "CONTENT_CREATOR_PASSWORD": "c",
               "CONTENT_REVIEWER_USERNAME": "reviewer_login", "CONTENT_REVIEWER_PASSWORD": "r",
               "TEST_USER_PASSWORD": "pw"}
    settings = Settings(env=env, volumes=vol, secrets=secrets)
    fake = FakeSunbird()
    fake.root_org = env["root_org_id"]
    store = Store(settings.output_dir / "state.db")
    client = SunbirdClient(settings, transport=httpx.MockTransport(fake))
    ctx = Ctx(settings, store, client)

    for stage in (users, content, courses, batches, enrolments):
        assert await stage.seed(ctx) == 0
    assert len(fake.enrolled) == 3 * 8

    # Rerun is a no-op: nothing new is created.
    before = next(fake.ids)
    for stage in (users, content, courses, batches, enrolments):
        assert await stage.seed(ctx) == 0
    assert next(fake.ids) == before + 1

    assert report(store, vol)
    csv_dir = export_all(store, settings.output_dir, workers=2, password="pw")
    rows = list(csv.DictReader(open(csv_dir / "enrolments_worker1.csv"))) + \
           list(csv.DictReader(open(csv_dir / "enrolments_worker2.csv")))
    assert len(rows) == 24 and "accessToken" not in rows[0]
    assert all(r["userName"].endswith("_t1") and r["password"] == "pw" for r in rows)
    user_rows = list(csv.DictReader(open(csv_dir / "users_worker1.csv")))
    assert list(user_rows[0]) == ["userId", "userName", "password"]
    assert user_rows[0]["password"] == "pw"
    w1 = {r["userId"] for r in csv.DictReader(open(csv_dir / "users_worker1.csv"))}
    w2 = {r["userId"] for r in csv.DictReader(open(csv_dir / "users_worker2.csv"))}
    assert w1 and w2 and not (w1 & w2)
    content_ids = [r["contentId"] for r in csv.DictReader(open(csv_dir / "content.csv"))]
    course_ids = [r["courseId"] for r in csv.DictReader(open(csv_dir / "courses.csv"))]
    assert len(content_ids) == len(set(content_ids)) == 12   # each Live ID once
    assert len(course_ids) == len(set(course_ids)) == 3
    await client.close()
