from seeder.state.store import Store


def test_upsert_merges_data_and_clears_error(tmp_path):
    s = Store(tmp_path / "s.db")
    s.upsert("content", "c1", "created", remote_id="do_1", data={"a": 1})
    s.mark_error("content", "c1", "boom")
    assert s.get("content", "c1")["error"] == "boom"
    s.upsert("content", "c1", "uploaded", data={"b": 2})
    rec = s.get("content", "c1")
    assert rec["status"] == "uploaded"
    assert rec["remote_id"] == "do_1"
    assert rec["data"] == {"a": 1, "b": 2}
    assert rec["error"] is None


def test_mark_error_keeps_last_status(tmp_path):
    s = Store(tmp_path / "s.db")
    s.upsert("user", "u1", "created", remote_id="x")
    s.mark_error("user", "u1", "e1")
    s.mark_error("user", "u1", "e2")
    rec = s.get("user", "u1")
    assert rec["status"] == "created" and rec["attempts"] == 2
