from collections import Counter

from seeder import plan


def test_enrolment_volume_matches_sheet():
    pairs = {(c, u) for c in range(1, 106)
             for u in plan.batch_user_indices(c, 500, 10000)}
    assert len(pairs) == 52500
    per_user = Counter(u for _, u in pairs)
    assert set(per_user.values()) <= {5, 6}


def test_course_contents_are_valid_and_distinct():
    for c in range(1, 106):
        idx = plan.course_content_indices(c, 10, 1000)
        assert len(set(idx)) == 10 and all(1 <= i <= 1000 for i in idx)


def test_split_units_even():
    assert [len(u) for u in plan.split_units(list(range(10)), 3)] == [4, 3, 3]


def test_worker_split_has_no_overlap():
    owners = {u: plan.worker_for_user(u, 4) for u in range(1, 10001)}
    assert Counter(owners.values()) == {1: 2500, 2: 2500, 3: 2500, 4: 2500}


def test_user_key_is_readable_and_run_scoped():
    assert plan.user_key("bench01", 1) == "user1_bench01"
    assert plan.user_key("bench01", 10000) == "user10000_bench01"


def test_content_mime_is_deterministic_and_mixed():
    picks = [plan.content_mime("r1", i, 0.3) for i in range(1, 201)]
    assert picks == [plan.content_mime("r1", i, 0.3) for i in range(1, 201)]
    assert 0 < picks.count("video/mp4") < 200 and "application/pdf" in picks
    assert {plan.content_mime("r1", i, 0) for i in range(1, 50)} == {"application/pdf"}
