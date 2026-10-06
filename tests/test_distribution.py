from collections import Counter

from seeder.export.distribution import weighted_rows


def test_reproducible():
    ids = [f"id{i}" for i in range(100)]
    assert weighted_rows(ids, 1000, 1.0, 7) == weighted_rows(ids, 1000, 1.0, 7)


def test_skew_creates_hot_ids():
    ids = [f"id{i}" for i in range(1000)]
    top10 = sum(n for _, n in Counter(weighted_rows(ids, 20000, 1.0, 1)).most_common(10))
    uniform_top10 = sum(n for _, n in Counter(weighted_rows(ids, 20000, 0.0, 1)).most_common(10))
    assert top10 > 3 * uniform_top10
