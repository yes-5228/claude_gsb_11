"""巡查路线接口测试：计划路线、路线比对、偏离说明约束。"""

from datetime import datetime, timedelta

import pytest

BASE = "/api/v1"


def _make_restrooms(client, count=3) -> list[dict]:
    rooms = []
    for index in range(count):
        response = client.post(
            f"{BASE}/restrooms",
            json={
                "name": f"路线测试公厕{index + 1}",
                "district": "路线测试区",
                "address": f"测试路 {index + 1} 号",
                "manager": "测试员",
            },
        )
        assert response.status_code == 201, response.text
        rooms.append(response.json())
    return rooms


def _make_plan(client, rooms, **overrides) -> dict:
    payload = {
        "name": "早班测试路线",
        "district": "路线测试区",
        "inspector": "张巡查",
        "shift": "早班",
        "points": [
            {"restroom_id": room["id"], "stay_minutes": 15} for room in rooms
        ],
    }
    payload.update(overrides)
    response = client.post(f"{BASE}/patrol-plans", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _tracks(rooms, start: datetime, stay=15, gap=10) -> list[dict]:
    """按顺序生成覆盖全部点位的轨迹。"""
    tracks = []
    cursor = start
    for room in rooms:
        arrive = cursor + timedelta(minutes=gap)
        leave = arrive + timedelta(minutes=stay)
        tracks.append(
            {
                "restroom_id": room["id"],
                "arrive_time": arrive.isoformat(),
                "leave_time": leave.isoformat(),
            }
        )
        cursor = leave
    return tracks


def _record_payload(plan, rooms, start: datetime, tracks) -> dict:
    last_leave = datetime.fromisoformat(tracks[-1]["leave_time"])
    return {
        "plan_id": plan["id"],
        "inspector": "张巡查",
        "start_time": start.isoformat(),
        "end_time": (last_leave + timedelta(minutes=5)).isoformat(),
        "tracks": tracks,
    }


@pytest.fixture
def plan_with_rooms(client):
    rooms = _make_restrooms(client, 3)
    plan = _make_plan(client, rooms)
    return plan, rooms


def test_plan_crud_and_validation(client):
    rooms = _make_restrooms(client, 3)
    plan = _make_plan(client, rooms)
    assert plan["record_count"] == 0
    assert [point["restroom_name"] for point in plan["points"]] == [r["name"] for r in rooms]

    listed = client.get(f"{BASE}/patrol-plans", params={"district": "路线测试区"}).json()
    assert listed["meta"]["total"] >= 1

    updated = client.patch(
        f"{BASE}/patrol-plans/{plan['id']}", json={"name": "改后路线", "shift": "晚班"}
    ).json()
    assert updated["name"] == "改后路线"
    assert updated["shift"] == "晚班"

    # 点位重复 / 点位为空 / 公厕不存在
    dup = client.post(
        f"{BASE}/patrol-plans",
        json={
            "name": "重复点位路线",
            "district": "路线测试区",
            "inspector": "张巡查",
            "points": [
                {"restroom_id": rooms[0]["id"]},
                {"restroom_id": rooms[0]["id"]},
            ],
        },
    )
    assert dup.status_code == 400

    empty = client.post(
        f"{BASE}/patrol-plans",
        json={"name": "空路线", "district": "路线测试区", "inspector": "张巡查", "points": []},
    )
    assert empty.status_code == 422

    missing = client.post(
        f"{BASE}/patrol-plans",
        json={
            "name": "不存在点位",
            "district": "路线测试区",
            "inspector": "张巡查",
            "points": [{"restroom_id": 999999}],
        },
    )
    assert missing.status_code == 400


def test_record_full_arrival_no_deviation(client, plan_with_rooms):
    plan, rooms = plan_with_rooms
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    payload = _record_payload(plan, rooms, start, _tracks(rooms, start))
    record = client.post(f"{BASE}/patrol-records", json=payload).json()

    assert record["arrival_rate"] == 100.0
    assert record["deviation_level"] == "无偏离"
    assert record["deviation"] == {"missed": [], "extra": [], "out_of_order": False}
    assert record["plan_name"] == plan["name"]
    assert record["duration_minutes"] > 0
    assert record["tracks"][0]["stay_minutes"] == 15
    assert record["tracks"][0]["restroom_name"] == rooms[0]["name"]


def test_significant_deviation_requires_note(client, plan_with_rooms):
    plan, rooms = plan_with_rooms
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    # 只到访 1 个点位：漏巡 2 个、到位率 33.3%，构成明显偏离
    tracks = _tracks(rooms[:1], start)
    payload = _record_payload(plan, rooms, start, tracks)

    rejected = client.post(f"{BASE}/patrol-records", json=payload)
    assert rejected.status_code == 400
    assert "偏离说明" in rejected.json()["detail"]

    accepted = client.post(
        f"{BASE}/patrol-records", json={**payload, "deviation_note": "暴雨导致末段点位车巡抽查"}
    )
    assert accepted.status_code == 201, accepted.text
    record = accepted.json()
    assert record["arrival_rate"] == pytest.approx(33.3, abs=0.1)
    assert record["deviation_level"] == "明显偏离"
    assert [p["restroom_id"] for p in record["deviation"]["missed"]] == [
        rooms[1]["id"],
        rooms[2]["id"],
    ]
    assert record["deviation_note"] == "暴雨导致末段点位车巡抽查"

    # 列表可按偏离程度过滤
    filtered = client.get(f"{BASE}/patrol-records", params={"deviation_level": "明显偏离"}).json()
    assert filtered["meta"]["total"] >= 1
    assert all(item["deviation_level"] == "明显偏离" for item in filtered["items"])


def test_minor_deviation_order_and_extra(client, plan_with_rooms):
    plan, rooms = plan_with_rooms
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

    # 顺序颠倒：全部到位但顺序与计划不一致 -> 轻微偏离
    swapped = [rooms[1], rooms[0], rooms[2]]
    record = client.post(
        f"{BASE}/patrol-records",
        json=_record_payload(plan, rooms, start, _tracks(swapped, start)),
    ).json()
    assert record["arrival_rate"] == 100.0
    assert record["deviation_level"] == "轻微偏离"
    assert record["deviation"]["out_of_order"] is True

    # 计划外点位：额外到访一座公厕 -> 轻微偏离
    outsider = client.post(
        f"{BASE}/restrooms",
        json={"name": "计划外公厕", "district": "路线测试区", "address": "测试路 9 号", "manager": "测试员"},
    ).json()
    tracks = _tracks(rooms, start) + _tracks([outsider], start + timedelta(hours=2))
    payload = _record_payload(plan, rooms, start, tracks)
    extra_record = client.post(f"{BASE}/patrol-records", json=payload).json()
    assert extra_record["deviation_level"] == "轻微偏离"
    assert [p["restroom_id"] for p in extra_record["deviation"]["extra"]] == [outsider["id"]]


def test_record_time_validation(client, plan_with_rooms):
    plan, rooms = plan_with_rooms
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

    # 结束时间早于开始时间
    bad_range = _record_payload(plan, rooms, start, _tracks(rooms, start))
    bad_range["end_time"] = (start - timedelta(hours=1)).isoformat()
    response = client.post(f"{BASE}/patrol-records", json=bad_range)
    assert response.status_code == 400

    # 轨迹离开时间早于到达时间
    tracks = _tracks(rooms, start)
    tracks[0]["leave_time"], tracks[0]["arrive_time"] = (
        tracks[0]["arrive_time"],
        tracks[0]["leave_time"],
    )
    response = client.post(
        f"{BASE}/patrol-records", json=_record_payload(plan, rooms, start, tracks)
    )
    assert response.status_code == 400

    # 轨迹超出巡查起止时间（结束时间早于最后点位的离开时间）
    tracks = _tracks(rooms, start)
    payload = _record_payload(plan, rooms, start, tracks)
    payload["end_time"] = (
        datetime.fromisoformat(tracks[-1]["leave_time"]) - timedelta(minutes=1)
    ).isoformat()
    response = client.post(f"{BASE}/patrol-records", json=payload)
    assert response.status_code == 400


def test_record_update_and_note_amend(client, plan_with_rooms):
    plan, rooms = plan_with_rooms
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    tracks = _tracks(rooms[:1], start)
    payload = {**_record_payload(plan, rooms, start, tracks), "deviation_note": "初始说明"}
    record = client.post(f"{BASE}/patrol-records", json=payload).json()
    assert record["deviation_level"] == "明显偏离"

    # 补充/修改偏离说明
    amended = client.patch(
        f"{BASE}/patrol-records/{record['id']}", json={"deviation_note": "补充：次日已完成补巡"}
    ).json()
    assert amended["deviation_note"] == "补充：次日已完成补巡"

    # 明显偏离的记录不允许清空说明
    cleared = client.patch(f"{BASE}/patrol-records/{record['id']}", json={"deviation_note": ""})
    assert cleared.status_code == 400

    # 更新轨迹为全部到访后，偏离等级重算为无偏离（轨迹变长，需同步延长结束时间）
    full_tracks = _tracks(rooms, start)
    last_leave = datetime.fromisoformat(full_tracks[-1]["leave_time"])
    full = client.patch(
        f"{BASE}/patrol-records/{record['id']}",
        json={
            "tracks": full_tracks,
            "end_time": (last_leave + timedelta(minutes=5)).isoformat(),
        },
    ).json()
    assert full["deviation_level"] == "无偏离"
    assert full["arrival_rate"] == 100.0


def test_plan_delete_guard(client, plan_with_rooms):
    plan, rooms = plan_with_rooms
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    client.post(
        f"{BASE}/patrol-records",
        json=_record_payload(plan, rooms, start, _tracks(rooms, start)),
    )

    blocked = client.delete(f"{BASE}/patrol-plans/{plan['id']}")
    assert blocked.status_code == 409

    ok = client.delete(f"{BASE}/patrol-plans/{plan['id']}", params={"force": "true"})
    assert ok.status_code == 200
    assert client.get(f"{BASE}/patrol-plans/{plan['id']}").status_code == 404
    # 级联删除后记录也不存在
    records = client.get(f"{BASE}/patrol-records", params={"plan_id": plan["id"]}).json()
    assert records["meta"]["total"] == 0
