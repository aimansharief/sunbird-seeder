"""Deterministic naming and assignment. Pure functions, no I/O."""
from __future__ import annotations


def user_key(run_id: str, i: int) -> str:
    """Also the Sunbird userName, e.g. user1_bench01."""
    return f"user{i}_{run_id}"


def content_key(run_id: str, i: int) -> str:
    return f"{run_id}_content_{i:05d}"


def course_key(run_id: str, i: int) -> str:
    return f"{run_id}_course_{i:04d}"


def batch_key(run_id: str, i: int) -> str:
    return f"{run_id}_batch_{i:04d}"


def enrol_key(run_id: str, course_i: int, user_i: int) -> str:
    return f"{run_id}_enrol_{course_i:04d}_{user_i:05d}"


def course_content_indices(course_i: int, contents_per_course: int,
                           total_contents: int) -> list[int]:
    """1-based content indices for a 1-based course index, round-robin."""
    start = (course_i - 1) * contents_per_course
    return [((start + t) % total_contents) + 1 for t in range(contents_per_course)]


def batch_user_indices(course_i: int, users_per_batch: int,
                       total_users: int) -> list[int]:
    """1-based user indices enrolled in a course's batch. Distinct within a batch."""
    if users_per_batch > total_users:
        raise ValueError("users_per_batch cannot exceed total users")
    start = (course_i - 1) * users_per_batch
    return [((start + k) % total_users) + 1 for k in range(users_per_batch)]


def split_units(items: list, units: int) -> list[list]:
    """Split children across course units as evenly as possible."""
    units = max(1, min(units, len(items))) if items else 1
    size, extra = divmod(len(items), units)
    out, pos = [], 0
    for u in range(units):
        n = size + (1 if u < extra else 0)
        out.append(items[pos:pos + n])
        pos += n
    return out


def worker_for_user(user_i: int, workers: int) -> int:
    """1-based JMeter worker that owns a user, so no user appears on two workers."""
    return ((user_i - 1) % workers) + 1
