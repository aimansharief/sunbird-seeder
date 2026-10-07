"""The runner stops starting new work after the first failure."""
import pytest

from seeder.stages.runner import poll_until, run_all
from seeder.state.store import Store


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None
    monkeypatch.setattr("seeder.stages.runner.asyncio.sleep", instant)


async def test_run_all_stops_after_first_failure(tmp_path):
    store = Store(tmp_path / "s.db")
    started = []

    async def worker(key):
        started.append(key)
        if key == "k2":
            raise RuntimeError("boom")

    failed = await run_all("t", "user", ["k1", "k2", "k3", "k4"], worker, store, concurrency=1)
    assert failed == 1 and started == ["k1", "k2"]
    assert "boom" in store.get("user", "k2")["error"]


async def test_poll_stops_when_a_status_read_fails(tmp_path):
    store = Store(tmp_path / "s.db")
    rounds = []

    async def check(key):
        rounds.append(key)
        raise RuntimeError("read failed")

    pending = await poll_until("t", "content", ["c1"], check, store, concurrency=1,
                               interval_s=0, timeout_s=60)
    assert pending == ["c1"] and rounds == ["c1"]          # one attempt, no further rounds
    assert "read failed" in store.get("content", "c1")["error"]
