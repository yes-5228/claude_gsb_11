"""巡查路线与执行记录接口测试：路线 CRUD、比对规则、偏离说明强制校验。"""

from datetime import datetime, timedelta

import pytest

BASE_TIME = datetime(2026, 9, 18, 8, 0, 0)


def _make_restroom(client, name: str) -> dict:
    response = client.post(
        "/api/v1/restrooms",
        json={"name": name, "district": "测试区", "address": "测试路 1 号", "manager": "测试员"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def route(client) -> dict:
    restrooms = [_make_restroom(client, f"路线点位{i}") for i in range(3)]
    response = client.post(
        "/api/v1/patrol-routes",
        json={
            "name": "测试巡查线",
            "district": "测试区",
            "shift": "早班",
            "points": [
                {"restroom_id": restrooms[0]["id"], "stay_minutes": 10},
                {"restroom_id": restrooms[1]["id"], "stay_minutes": 10},
                {"restroom_id": restrooms[2]["id"], "stay_minutes": 15},
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    payload["_restrooms"] = restrooms
    return payload


def _visit_all(route: dict, stay: int = 20) -> list[dict]:
    """生成按顺序、停留充足的实际轨迹。"""
    points = []
    cursor = BASE_TIME
    for point in route["points"]:
        arrive = cursor + timedelta(minutes=10)
        leave = arrive + timedelta(minutes=stay)
        points.append(
            {
                "restroom_id": point["restroom_id"],
                "arrive_at": arrive.isoformat(),
                "leave_at": leave.isoformat(),
            }
        )
        cursor = leave
    return points


def _create_record(client, route: dict, actual_points: list[dict], **extra):
    payload = {
        "route_id": route["id"],
        "inspector": "测试巡查员",
        "start_time": BASE_TIME.isoformat(),
        "end_time": (BASE_TIME + timedelta(hours=2)).isoformat(),
        "actual_points": actual_points,
    }
    payload.update(extra)
    return client.post("/api/v1/patrol-records", json=payload)


def test_route_crud_and_validation(client, route):
    assert route["name"] == "测试巡查线"
    assert len(route["points"]) == 3
    assert route["points"][0]["restroom_name"].startswith("路线点位")

    listed = client.get("/api/v1/patrol-routes", params={"district": "测试区"}).json()
    assert any(item["id"] == route["id"] for item in listed)

    updated = client.patch(
        f"/api/v1/patrol-routes/{route['id']}", json={"name": "改名巡查线", "enabled": False}
    ).json()
    assert updated["name"] == "改名巡查线"
    assert updated["enabled"] is False

    # 点位重复 / 公厕不存在 / 点位为空均被拒绝
    restrooms = route["_restrooms"]
    duplicate = client.post(
        "/api/v1/patrol-routes",
        json={
            "name": "重复点位线",
            "district": "测试区",
            "points": [
                {"restroom_id": restrooms[0]["id"], "stay_minutes": 5},
                {"restroom_id": restrooms[0]["id"], "stay_minutes": 5},
            ],
        },
    )
    assert duplicate.status_code == 400

    missing = client.post(
        "/api/v1/patrol-routes",
        json={
            "name": "不存在点位线",
            "district": "测试区",
            "points": [{"restroom_id": 999999, "stay_minutes": 5}],
        },
    )
    assert missing.status_code == 400

    empty = client.post(
        "/api/v1/patrol-routes", json={"name": "空路线", "district": "测试区", "points": []}
    )
    assert empty.status_code == 422


def test_record_full_arrival(client, route):
    response = _create_record(client, route, _visit_all(route))
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["planned_count"] == 3
    assert record["arrived_count"] == 3
    assert record["arrival_rate"] == 100.0
    assert record["is_deviated"] is False
    assert record["deviations"] == []
    assert record["duration_minutes"] == 120
    assert [p["stay_minutes"] for p in record["actual_points"]] == [20, 20, 20]


def test_record_missed_point_requires_note(client, route):
    points = _visit_all(route)[:2]  # 漏掉第三个点位

    rejected = _create_record(client, route, points)
    assert rejected.status_code == 400
    assert "偏离说明" in rejected.json()["detail"]

    accepted = _create_record(client, route, points, deviation_note="第三个点位道路施工，已报备")
    assert accepted.status_code == 201, accepted.text
    record = accepted.json()
    assert record["arrived_count"] == 2
    assert record["arrival_rate"] == pytest.approx(66.7, abs=0.1)
    assert record["is_deviated"] is True
    assert record["deviation_note"] == "第三个点位道路施工，已报备"
    missed = [d for d in record["deviations"] if d["type"] == "漏巡"]
    assert len(missed) == 1
    assert missed[0]["restroom_id"] == route["points"][2]["restroom_id"]


def test_record_short_stay_and_extra_point(client, route):
    points = _visit_all(route)
    # 第一个点位只停留 5 分钟（计划 10 分钟）
    first = points[0]
    arrive = datetime.fromisoformat(first["arrive_at"])
    first["leave_at"] = (arrive + timedelta(minutes=5)).isoformat()
    # 追加一个计划外点位
    extra_restroom = _make_restroom(client, "计划外公厕")
    last_leave = datetime.fromisoformat(points[-1]["leave_at"])
    points.append(
        {
            "restroom_id": extra_restroom["id"],
            "arrive_at": (last_leave + timedelta(minutes=10)).isoformat(),
            "leave_at": (last_leave + timedelta(minutes=20)).isoformat(),
        }
    )

    record = _create_record(client, route, points).json()
    assert record["arrival_rate"] == 100.0
    assert record["is_deviated"] is False  # 停留不足/计划外不视为偏离明显
    types = {d["type"] for d in record["deviations"]}
    assert types == {"停留不足", "计划外点位"}
    extra_out = [p for p in record["actual_points"] if p["restroom_id"] == extra_restroom["id"]]
    assert extra_out[0]["planned"] is False


def test_record_out_of_order(client, route):
    points = _visit_all(route)
    # 交换前两个点位的到访时间：先巡第二个点位，再巡第一个
    points[0]["arrive_at"], points[1]["arrive_at"] = points[1]["arrive_at"], points[0]["arrive_at"]
    points[0]["leave_at"], points[1]["leave_at"] = points[1]["leave_at"], points[0]["leave_at"]
    record = _create_record(client, route, points).json()
    assert record["arrival_rate"] == 100.0
    assert record["is_deviated"] is False
    assert any(d["type"] == "顺序偏离" for d in record["deviations"])


def test_record_filters_and_delete(client, route):
    _create_record(client, route, _visit_all(route))
    missed = _create_record(
        client, route, _visit_all(route)[:1], deviation_note="突发情况，两个点位未巡"
    ).json()

    deviated = client.get("/api/v1/patrol-records", params={"is_deviated": "true"}).json()
    assert deviated["meta"]["total"] >= 1
    assert all(item["is_deviated"] for item in deviated["items"])

    by_route = client.get("/api/v1/patrol-records", params={"route_id": route["id"]}).json()
    assert by_route["meta"]["total"] == 2

    removed = client.delete(f"/api/v1/patrol-records/{missed['id']}")
    assert removed.status_code == 200
    assert client.get(f"/api/v1/patrol-records/{missed['id']}").status_code == 404


def test_route_delete_guard_and_disabled_route(client, route):
    _create_record(client, route, _visit_all(route))

    blocked = client.delete(f"/api/v1/patrol-routes/{route['id']}")
    assert blocked.status_code == 409

    client.patch(f"/api/v1/patrol-routes/{route['id']}", json={"enabled": False})
    rejected = _create_record(client, route, _visit_all(route))
    assert rejected.status_code == 400
    assert "停用" in rejected.json()["detail"]

    forced = client.delete(f"/api/v1/patrol-routes/{route['id']}", params={"force": "true"})
    assert forced.status_code == 200
    assert client.get(f"/api/v1/patrol-routes/{route['id']}").status_code == 404
    remaining = client.get("/api/v1/patrol-records", params={"route_id": route["id"]}).json()
    assert remaining["meta"]["total"] == 0


def test_record_time_validation(client, route):
    bad_point = _visit_all(route)[:1]
    bad_point[0]["leave_at"] = bad_point[0]["arrive_at"]  # 离开早于到达
    bad_point[0]["arrive_at"] = (BASE_TIME + timedelta(minutes=30)).isoformat()
    response = _create_record(client, route, bad_point)
    assert response.status_code == 422

    response = _create_record(
        client,
        route,
        _visit_all(route),
        start_time=(BASE_TIME + timedelta(hours=3)).isoformat(),
        end_time=BASE_TIME.isoformat(),
    )
    assert response.status_code == 422
