"""Runs every stage, tokens and export against an in-memory fake Sunbird."""
import csv
import itertools
import json

import httpx
import pytest
import yaml

from seeder.client.http import SunbirdClient
from seeder.config import Settings
from seeder.export.csv_export import export_all
from seeder.stages import batches, content, courses, enrolments, tokens, users
from seeder.stages.context import Ctx
from seeder.state.store import Store
from seeder.verify import report


class FakeSunbird:
    def __init__(self):
        self.ids = itertools.count(1)
        self.status = {}
        self.enrolled = set()
        self.flaky_once = True

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        ok = lambda result: httpx.Response(200, json={"result": result})
        if p.endswith("/token"):
            return httpx.Response(200, json={"access_token": f"tok{next(self.ids)}",
                                             "expires_in": 600})
        if p == "/api/user/v1/create":
            if self.flaky_once:          # exercise the retry path once
                self.flaky_once = False
                return httpx.Response(503)
            return ok({"userId": f"user-{next(self.ids)}"})
        if p in ("/api/content/v1/create", "/api/collection/v1/create"):
            ident = f"do_{next(self.ids)}"
            self.status[ident] = "Draft"
            return ok({"identifier": ident})
        if "/upload/" in p:
            return ok({"content_url": "https://cdn/x.pdf"})
        if "/review/" in p:
            self.status[p.rsplit("/", 1)[1]] = "Review"
            return ok({})
        if "/publish/" in p:
            self.status[p.rsplit("/", 1)[1]] = "Live"
            return ok({})
        if "/read/" in p:
            return ok({"content": {"status": self.status[p.rsplit("/", 1)[1]]}})
        if p == "/api/collection/v1/hierarchy/update":
            return ok({})
        if p == "/api/course/v1/batch/create":
            return ok({"batchId": f"batch-{next(self.ids)}"})
        if p == "/api/course/v1/enrol":
            r = json.loads(req.content)["request"]
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
    repo_asset = os.path.join(os.path.dirname(__file__), "..", "assets", "sample_content.pdf")
    shutil.copy(repo_asset, "assets/sample_content.pdf")

    with open(os.path.join(os.path.dirname(__file__), "..", "config", "bench.yaml")) as f:
        env = yaml.safe_load(f)
    env.update(base_url="https://sb.test", output_root=str(tmp_path), retries=2)
    env["publish_poll"] = {"interval_s": 0, "timeout_s": 5}
    vol = {"run_id": "t1", "users": 20, "contents": 12, "courses": 3,
           "contents_per_course": 4, "units_per_course": 2, "users_per_batch": 8,
           "export": {"read_rows": 50, "skew": 1.0, "seed": 1}}
    secrets = {"SUNBIRD_API_KEY": "k", "ADMIN_USERNAME": "a", "ADMIN_PASSWORD": "p",
               "ADMIN_USER_ID": "admin", "TEST_USER_PASSWORD": "pw"}
    settings = Settings(env=env, volumes=vol, secrets=secrets)
    fake = FakeSunbird()
    store = Store(settings.output_dir / "state.db")
    client = SunbirdClient(settings, transport=httpx.MockTransport(fake))
    ctx = Ctx(settings, store, client)

    for stage in (users, content, courses, batches, enrolments):
        assert await stage.seed(ctx) == 0
    assert await tokens.refresh(ctx) == 0
    assert len(fake.enrolled) == 3 * 8

    # Rerun is a no-op: nothing new is created.
    before = next(fake.ids)
    for stage in (users, content, courses, batches, enrolments):
        assert await stage.seed(ctx) == 0
    assert next(fake.ids) == before + 1

    assert report(store, vol)
    csv_dir = export_all(store, vol, settings.output_dir, workers=2)
    rows = list(csv.DictReader(open(csv_dir / "enrolments_worker1.csv"))) + \
           list(csv.DictReader(open(csv_dir / "enrolments_worker2.csv")))
    assert len(rows) == 24 and all(r["accessToken"] for r in rows)
    w1 = {r["userId"] for r in csv.DictReader(open(csv_dir / "users_worker1.csv"))}
    w2 = {r["userId"] for r in csv.DictReader(open(csv_dir / "users_worker2.csv"))}
    assert w1 and w2 and not (w1 & w2)
    assert len(list(csv.DictReader(open(csv_dir / "content.csv")))) == 50
    await client.close()
