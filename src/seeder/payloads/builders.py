"""Request bodies. VERIFY field names against your Spark deployment."""
from __future__ import annotations

import uuid
from datetime import date


def user_create(key: str, index: int, env: dict, password: str) -> dict:
    return {"request": {
        "firstName": "User",
        "lastName": str(index),
        "userName": key,
        "email": f"{key}@{env['email_domain']}",
        "emailVerified": True,
        "password": password,
        "dob": "2001",
        "channel": env["channel"],
        "roles": ["PUBLIC"],
    }}


def user_search_by_username(username: str) -> dict:
    return {"request": {"filters": {"userName": username}, "fields": ["id", "userName"]}}


def content_create(key: str, env: dict, created_by: str, creator: str, mime_type: str) -> dict:
    return {"request": {"content": {
        "name": key,
        "code": key,
        "mimeType": mime_type,
        "primaryCategory": "Learning Resource",
        "channel": env["channel"],
        "createdBy": created_by,
        "creator": creator,
        "framework": env["framework"],
    }}}


def course_create(key: str, env: dict, created_by: str, creator: str) -> dict:
    return {"request": {"content": {
        "name": key,
        "code": key,
        "mimeType": "application/vnd.ekstep.content-collection",
        "primaryCategory": "Course",
        "channel": env["channel"],
        "createdBy": created_by,
        "creator": creator,
        "framework": env["framework"],
    }}}


def course_hierarchy(course_id: str, course_name: str, units: list[list[str]],
                     updated_by: str, unit_ids: list[str], new: bool) -> dict:
    """One course, N units, each holding Live content IDs.

    new=True creates the units (unit_ids are temporary). new=False re-sends the tree keyed by
    the real unit IDs, so the server's relational_metadata is keyed by the IDs publish reads.
    """
    nodes = {course_id: {"root": True, "isNew": False, "objectType": "Content",
                         "metadata": {"name": course_name}}}
    hierarchy = {course_id: {"name": course_name, "contentType": "Course",
                             "root": True, "children": list(unit_ids)}}
    for n, (unit_id, children) in enumerate(zip(unit_ids, units), start=1):
        unit_name = f"{course_name} Unit {n}"
        if new:
            nodes[unit_id] = {"root": False, "isNew": True, "objectType": "Collection",
                              "metadata": {
                                  "code": unit_id,
                                  "name": unit_name,
                                  "mimeType": "application/vnd.ekstep.content-collection",
                                  "primaryCategory": "Course Unit",
                                  "contentType": "CourseUnit",
                                  "visibility": "Parent",
                                  "dialcodeRequired": "No",
                                  "attributions": [],
                              }}
        hierarchy[unit_id] = {"name": unit_name, "contentType": "CourseUnit",
                              "root": False, "children": list(children)}
    return {"request": {"data": {"nodesModified": nodes, "hierarchy": hierarchy,
                                 "lastUpdatedBy": updated_by}}}


def review() -> dict:
    return {"request": {"content": {}}}


def publish(published_by: str) -> dict:
    return {"request": {"content": {"lastPublishedBy": published_by}}}


def batch_create(key: str, course_id: str, env: dict, created_by: str) -> dict:
    return {"request": {
        "courseId": course_id,
        "name": key,
        "description": "Benchmark seed batch",
        "enrollmentType": "open",
        "startDate": date.today().isoformat(),
        "endDate": None,
        "createdBy": created_by,
        "createdFor": [env["root_org_id"]],
        "mentors": [],
        "tandc": True,
    }}


def enrol(user_id: str, course_id: str, batch_id: str) -> dict:
    return {"request": {"userId": user_id, "courseId": course_id, "batchId": batch_id}}
