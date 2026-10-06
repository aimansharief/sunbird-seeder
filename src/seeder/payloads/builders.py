"""Request bodies. VERIFY field names against your Spark deployment."""
from __future__ import annotations

import uuid
from datetime import date


def user_create(key: str, env: dict, password: str) -> dict:
    return {"request": {
        "firstName": "Bench",
        "lastName": key,
        "userName": key,
        "email": f"{key}@{env['email_domain']}",
        "emailVerified": True,
        "password": password,
        "channel": env["channel"],
    }}


def user_search_by_username(username: str) -> dict:
    return {"request": {"filters": {"userName": username}, "fields": ["id", "userName"]}}


def content_create(key: str, env: dict, created_by: str) -> dict:
    return {"request": {"content": {
        "name": key,
        "code": key,
        "mimeType": "application/pdf",
        "primaryCategory": "Learning Resource",
        "contentType": "Resource",
        "framework": env["framework"],
        "channel": env["channel"],
        "createdBy": created_by,
        "createdFor": [env["root_org_id"]],
        "description": "Benchmark seed content",
    }}}


def course_create(key: str, env: dict, created_by: str) -> dict:
    return {"request": {"content": {
        "name": key,
        "code": key,
        "mimeType": "application/vnd.ekstep.content-collection",
        "primaryCategory": "Course",
        "contentType": "Course",
        "framework": env["framework"],
        "channel": env["channel"],
        "createdBy": created_by,
        "createdFor": [env["root_org_id"]],
        "description": "Benchmark seed course",
    }}}


def course_hierarchy(course_id: str, units: list[list[str]]) -> dict:
    """One course with N units; each unit holds Live content IDs."""
    nodes = {course_id: {"root": True, "isNew": False, "metadata": {}}}
    hierarchy = {course_id: {"root": True, "children": []}}
    for n, children in enumerate(units, start=1):
        unit_id = str(uuid.uuid4())
        nodes[unit_id] = {"root": False, "isNew": True, "objectType": "Collection",
                          "metadata": {
                              "name": f"Unit {n}",
                              "mimeType": "application/vnd.ekstep.content-collection",
                              "primaryCategory": "Course Unit",
                              "contentType": "CourseUnit",
                              "visibility": "Parent",
                          }}
        hierarchy[course_id]["children"].append(unit_id)
        hierarchy[unit_id] = {"root": False, "children": list(children)}
    return {"request": {"data": {"nodesModified": nodes, "hierarchy": hierarchy}}}


def review() -> dict:
    return {"request": {"content": {}}}


def publish(published_by: str) -> dict:
    return {"request": {"content": {"lastPublishedBy": published_by}}}


def batch_create(key: str, course_id: str, created_by: str) -> dict:
    return {"request": {
        "courseId": course_id,
        "name": key,
        "description": "Benchmark seed batch",
        "enrollmentType": "open",
        "startDate": date.today().isoformat(),
        "createdBy": created_by,
    }}


def enrol(user_id: str, course_id: str, batch_id: str) -> dict:
    return {"request": {"userId": user_id, "courseId": course_id, "batchId": batch_id}}
