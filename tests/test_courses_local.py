"""Course stage in local mode against a fake knowlg v4: create -> hierarchy -> publish -> Live."""
import itertools
import json
import os
import shutil

import httpx
import yaml

from seeder.client.http import SunbirdClient
from seeder.config import Settings
from seeder.stages import content, courses
from seeder.stages.context import Ctx
from seeder.state.store import Store

from test_content_local import ROOT, FakeKnowlg


class FakeKnowlgCourses(FakeKnowlg):
    """Mimics the server: new units get real IDs, but relational_metadata keeps the request keys,
    and publish fails ("key not found") unless every unit's real ID is among those keys."""

    def __init__(self):
        super().__init__()
        self.hierarchies, self.rm_keys, self.updates = {}, {}, {}
        self.units = itertools.count(1)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        ok = lambda result: httpx.Response(200, json={"result": result})
        if p == "/collection/v4/hierarchy/update":
            data = json.loads(req.content)["request"]["data"]
            assert data["lastUpdatedBy"] == "creator-id"
            root = next(k for k, v in data["nodesModified"].items() if v["root"])
            assert data["nodesModified"][root]["metadata"]["name"].startswith("t1_course_")
            idmap = {}
            for k, v in data["nodesModified"].items():
                if v["isNew"]:
                    meta = v["metadata"]
                    assert meta["primaryCategory"] == "Course Unit" and meta["visibility"] == "Parent"
                    assert meta["code"] == k and meta["dialcodeRequired"] == "No"
                    idmap[k] = f"do_unit{next(self.units)}"
            units = [idmap.get(u, u) for u in data["hierarchy"][root]["children"]]
            self.hierarchies[root] = {idmap.get(u, u): data["hierarchy"][u]["children"]
                                      for u in data["hierarchy"][root]["children"]}
            self.rm_keys[root] = set(data["hierarchy"])           # stored as sent, never remapped
            self.updates[root] = self.updates.get(root, 0) + 1
            assert len(units) == len(data["hierarchy"][root]["children"])
            return ok({"content_id": root, "identifiers": idmap})
        if p.startswith("/collection/v4/publish/"):
            cid = p.rsplit("/", 1)[1]
            assert json.loads(req.content)["request"]["content"]["lastPublishedBy"] == "reviewer-id"
            ok_keys = all(u in self.rm_keys[cid] for u in self.hierarchies[cid])
            self.status[cid] = "Live" if ok_keys else "Failed"
            return ok({"publishStatus": "pushed"})
        if p.startswith("/collection/v4/read/"):
            return ok({"content": {"status": self.status[p.rsplit("/", 1)[1]]}})
        return super().__call__(req)


async def test_courses_local_v4(tmp_path, monkeypatch):
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
    vol = {"run_id": "t1", "contents": 12, "mp4_ratio": 0.5, "courses": 3,
           "contents_per_course": 4, "units_per_course": 2}
    settings = Settings(env=env, volumes=vol, secrets={
        "CONTENT_CREATOR_USERNAME": "creator1", "CONTENT_CREATOR_ID": "creator-id",
        "CONTENT_REVIEWER_USERNAME": "reviewer1", "CONTENT_REVIEWER_ID": "reviewer-id"})
    fake = FakeKnowlgCourses()
    fake.publish_failures = 0
    store = Store(settings.output_dir / "state.db")
    client = SunbirdClient(settings, transport=httpx.MockTransport(fake))
    ctx = Ctx(settings, store, client)

    assert await content.seed(ctx) == 0
    assert await courses.seed(ctx) == 0
    recs = store.list("course")
    assert [r["status"] for r in recs] == ["live"] * 3
    assert all(fake.mime[r["remote_id"]] == "application/vnd.ekstep.content-collection"
               for r in recs)
    content_ids = {r["remote_id"] for r in store.list("content")}
    for r in recs:
        placed = [i for kids in fake.hierarchies[r["remote_id"]].values() for i in kids]
        assert len(placed) == 4 and len(set(placed)) == 4 and set(placed) <= content_ids
        assert len(fake.hierarchies[r["remote_id"]]) == 2
        assert fake.updates[r["remote_id"]] == 2     # create units, then re-key by real IDs
    await client.close()
