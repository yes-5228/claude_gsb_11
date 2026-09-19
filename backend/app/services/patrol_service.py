"""巡查路线计划与巡查执行记录业务逻辑。"""

from datetime import date, datetime, time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ROUTE_ARRIVAL_RATE_THRESHOLD,
    ROUTE_STAY_TOLERANCE_MINUTES,
    RouteDeviationType,
)
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models import PatrolRecord, PatrolRoute, Restroom
from app.schemas.patrol import (
    ActualPointOut,
    PatrolRecordCreate,
    PatrolRecordOut,
    PatrolRouteCreate,
    PatrolRouteOut,
    PatrolRouteUpdate,
    RoutePointOut,
)

RECORD_SORTABLE_FIELDS = {
    "start_time": PatrolRecord.start_time,
    "arrival_rate": PatrolRecord.arrival_rate,
    "created_at": PatrolRecord.created_at,
}


def _restroom_names(db: Session, restroom_ids: list[int]) -> dict[int, Restroom]:
    """批量查询公厕，返回 id -> Restroom 映射。"""
    ids = sorted({rid for rid in restroom_ids if rid})
    if not ids:
        return {}
    rows = db.scalars(select(Restroom).where(Restroom.id.in_(ids)))
    return {row.id: row for row in rows}


def _normalize_route_points(db: Session, points: list) -> list[dict]:
    """校验并规范化计划点位：公厕必须存在且不重复。"""
    if not points:
        raise DomainError("路线点位不能为空")
    normalized: list[dict] = []
    seen: set[int] = set()
    for point in points:
        data = point.model_dump() if hasattr(point, "model_dump") else dict(point)
        restroom_id = int(data.get("restroom_id") or 0)
        if restroom_id in seen:
            raise DomainError(f"公厕 #{restroom_id} 在路线中重复")
        seen.add(restroom_id)
        normalized.append(
            {"restroom_id": restroom_id, "stay_minutes": int(data.get("stay_minutes") or 0)}
        )
    restrooms = _restroom_names(db, [p["restroom_id"] for p in normalized])
    missing = [p["restroom_id"] for p in normalized if p["restroom_id"] not in restrooms]
    if missing:
        raise DomainError(f"以下公厕不存在，无法加入路线：{missing}")
    return normalized


def compare_route(
    planned_points: list[dict],
    actual_points: list[dict],
    *,
    arrival_threshold: float = ROUTE_ARRIVAL_RATE_THRESHOLD,
    stay_tolerance: int = ROUTE_STAY_TOLERANCE_MINUTES,
) -> dict:
    """比对计划路线与实际轨迹，返回到位率与偏离明细。

    planned_points: [{restroom_id, stay_minutes, restroom_name?}]，顺序即计划顺序
    actual_points:  [{restroom_id, point_name?, arrive_at, leave_at}]
    """
    deviations: list[dict] = []
    planned_ids = [p["restroom_id"] for p in planned_points]
    planned_map = {p["restroom_id"]: p for p in planned_points}

    def _name(point: dict, fallback_id: int) -> str:
        return point.get("point_name") or point.get("restroom_name") or f"公厕#{fallback_id}"

    # 实际轨迹按计划点位/计划外点位拆分
    actual_planned: list[dict] = []
    for actual in actual_points:
        rid = actual["restroom_id"]
        if rid in planned_map:
            actual_planned.append(actual)
        else:
            deviations.append(
                {
                    "type": RouteDeviationType.EXTRA_POINT.value,
                    "restroom_id": rid,
                    "point_name": _name(actual, rid),
                    "detail": "该点位不在计划路线中",
                }
            )

    arrived_ids = {a["restroom_id"] for a in actual_planned}

    # 漏巡与停留不足
    for planned in planned_points:
        rid = planned["restroom_id"]
        name = _name(planned, rid)
        if rid not in arrived_ids:
            deviations.append(
                {
                    "type": RouteDeviationType.MISSED.value,
                    "restroom_id": rid,
                    "point_name": name,
                    "detail": "计划点位未巡查",
                }
            )
            continue
        actual = next(a for a in actual_planned if a["restroom_id"] == rid)
        stay = (actual["leave_at"] - actual["arrive_at"]).total_seconds() / 60
        required = planned["stay_minutes"] - stay_tolerance
        if stay < required:
            deviations.append(
                {
                    "type": RouteDeviationType.SHORT_STAY.value,
                    "restroom_id": rid,
                    "point_name": name,
                    "detail": f"计划停留 {planned['stay_minutes']} 分钟，实际停留 {int(stay)} 分钟",
                }
            )

    # 顺序偏离：计划内点位的实际到访顺序与计划顺序不一致
    visited_order = [
        a["restroom_id"]
        for a in sorted(actual_planned, key=lambda item: item["arrive_at"])
    ]
    expected_order = [rid for rid in planned_ids if rid in arrived_ids]
    if visited_order != expected_order:
        deviations.append(
            {
                "type": RouteDeviationType.OUT_OF_ORDER.value,
                "restroom_id": None,
                "point_name": "",
                "detail": "实际巡查顺序与计划路线不一致",
            }
        )

    planned_count = len(planned_points)
    arrived_count = len(arrived_ids)
    arrival_rate = round(arrived_count / planned_count * 100, 1) if planned_count else 0.0
    has_missed = any(d["type"] == RouteDeviationType.MISSED.value for d in deviations)
    is_deviated = arrival_rate < arrival_threshold or has_missed

    return {
        "planned_count": planned_count,
        "arrived_count": arrived_count,
        "arrival_rate": arrival_rate,
        "deviations": deviations,
        "is_deviated": is_deviated,
    }


# ---------------------------------------------------------------- 路线计划


def get_route(db: Session, route_id: int) -> PatrolRoute:
    route = db.get(PatrolRoute, route_id)
    if route is None:
        raise NotFoundError(f"巡查路线 {route_id} 不存在")
    return route


def route_to_out(db: Session, route: PatrolRoute) -> PatrolRouteOut:
    restrooms = _restroom_names(db, [p["restroom_id"] for p in route.points or []])
    points = []
    for point in route.points or []:
        restroom = restrooms.get(point["restroom_id"])
        points.append(
            RoutePointOut(
                restroom_id=point["restroom_id"],
                restroom_name=restroom.name if restroom else f"公厕#{point['restroom_id']}",
                restroom_code=restroom.code if restroom else "",
                stay_minutes=point["stay_minutes"],
            )
        )
    data = PatrolRouteOut.model_validate(route)
    data.points = points
    data.record_count = len(route.records)
    return data


def list_routes(
    db: Session,
    *,
    district: str | None = None,
    shift: str | None = None,
    enabled: bool | None = None,
    keyword: str | None = None,
) -> list[PatrolRoute]:
    stmt = select(PatrolRoute).order_by(PatrolRoute.id)
    if district:
        stmt = stmt.where(PatrolRoute.district == district)
    if shift:
        stmt = stmt.where(PatrolRoute.shift == shift)
    if enabled is not None:
        stmt = stmt.where(PatrolRoute.enabled == enabled)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(PatrolRoute.name.like(like), PatrolRoute.remark.like(like)))
    return list(db.scalars(stmt))


def create_route(db: Session, payload: PatrolRouteCreate) -> PatrolRoute:
    points = _normalize_route_points(db, payload.points)
    route = PatrolRoute(
        name=payload.name.strip(),
        district=payload.district.strip(),
        shift=payload.shift.value if hasattr(payload.shift, "value") else payload.shift,
        points=points,
        enabled=payload.enabled,
        remark=payload.remark,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


def update_route(db: Session, route_id: int, payload: PatrolRouteUpdate) -> PatrolRoute:
    route = get_route(db, route_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("points") is not None:
        route.points = _normalize_route_points(db, payload.points or [])
    if data.get("name") is not None:
        route.name = payload.name.strip()
    if data.get("district") is not None:
        route.district = payload.district.strip()
    if data.get("shift") is not None and payload.shift is not None:
        route.shift = payload.shift.value if hasattr(payload.shift, "value") else payload.shift
    if data.get("enabled") is not None:
        route.enabled = payload.enabled
    if "remark" in data:
        route.remark = payload.remark
    db.commit()
    db.refresh(route)
    return route


def delete_route(db: Session, route_id: int, *, force: bool = False) -> None:
    route = get_route(db, route_id)
    if route.records and not force:
        raise ConflictError(
            f"该路线已产生 {len(route.records)} 条巡查记录，确认级联删除请使用 force=true"
        )
    db.delete(route)
    db.commit()


# ---------------------------------------------------------------- 执行记录


def get_record(db: Session, record_id: int) -> PatrolRecord:
    record = db.get(PatrolRecord, record_id)
    if record is None:
        raise NotFoundError(f"巡查记录 {record_id} 不存在")
    return record


def record_to_out(record: PatrolRecord) -> PatrolRecordOut:
    planned_ids = {p["restroom_id"] for p in (record.route.points or [])} if record.route else set()
    points = []
    for point in record.actual_points or []:
        arrive = datetime.fromisoformat(str(point["arrive_at"]))
        leave = datetime.fromisoformat(str(point["leave_at"]))
        points.append(
            ActualPointOut(
                restroom_id=point["restroom_id"],
                point_name=point.get("point_name") or f"公厕#{point['restroom_id']}",
                arrive_at=arrive,
                leave_at=leave,
                stay_minutes=int((leave - arrive).total_seconds() // 60),
                planned=point["restroom_id"] in planned_ids,
            )
        )
    data = PatrolRecordOut.model_validate(record)
    data.route_name = record.route.name if record.route else ""
    data.actual_points = points
    data.duration_minutes = int((record.end_time - record.start_time).total_seconds() // 60)
    return data


def list_records(
    db: Session,
    *,
    route_id: int | None = None,
    district: str | None = None,
    inspector: str | None = None,
    is_deviated: bool | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "start_time",
    order: str = "desc",
) -> tuple[list[PatrolRecord], int]:
    stmt = select(PatrolRecord)
    if district:
        stmt = stmt.join(PatrolRoute, PatrolRoute.id == PatrolRecord.route_id).where(
            PatrolRoute.district == district
        )
    if route_id:
        stmt = stmt.where(PatrolRecord.route_id == route_id)
    if inspector:
        stmt = stmt.where(PatrolRecord.inspector.like(f"%{inspector.strip()}%"))
    if is_deviated is not None:
        stmt = stmt.where(PatrolRecord.is_deviated == is_deviated)
    if date_from:
        stmt = stmt.where(PatrolRecord.start_time >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(PatrolRecord.start_time <= datetime.combine(date_to, time.max))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                PatrolRecord.inspector.like(like),
                PatrolRecord.deviation_note.like(like),
                PatrolRecord.route_id.in_(
                    select(PatrolRoute.id).where(PatrolRoute.name.like(like))
                ),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = RECORD_SORTABLE_FIELDS.get(sort_by, PatrolRecord.start_time)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), PatrolRecord.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def create_record(db: Session, payload: PatrolRecordCreate) -> PatrolRecord:
    route = get_route(db, payload.route_id)
    if not route.enabled:
        raise DomainError("该路线已停用，无法登记巡查记录")

    restrooms = _restroom_names(db, [p.restroom_id for p in payload.actual_points])
    missing = [p.restroom_id for p in payload.actual_points if p.restroom_id not in restrooms]
    if missing:
        raise DomainError(f"以下公厕不存在，无法登记轨迹：{missing}")

    # 计划点位带上名称，便于偏离明细可读
    planned_points = []
    for point in route.points or []:
        restroom = restrooms.get(point["restroom_id"]) or db.get(Restroom, point["restroom_id"])
        planned_points.append(
            {
                "restroom_id": point["restroom_id"],
                "stay_minutes": point["stay_minutes"],
                "restroom_name": restroom.name if restroom else "",
            }
        )
    actual_points = [
        {
            "restroom_id": p.restroom_id,
            "point_name": restrooms[p.restroom_id].name,
            "arrive_at": p.arrive_at,
            "leave_at": p.leave_at,
        }
        for p in payload.actual_points
    ]

    result = compare_route(planned_points, actual_points)
    if result["is_deviated"] and not (payload.deviation_note or "").strip():
        raise DomainError(
            f"本次巡查到位率 {result['arrival_rate']}%，存在明显偏离，必须填写偏离说明"
        )

    record = PatrolRecord(
        route_id=route.id,
        inspector=payload.inspector.strip(),
        start_time=payload.start_time,
        end_time=payload.end_time,
        actual_points=[
            {**p, "arrive_at": p["arrive_at"].isoformat(), "leave_at": p["leave_at"].isoformat()}
            for p in actual_points
        ],
        planned_count=result["planned_count"],
        arrived_count=result["arrived_count"],
        arrival_rate=result["arrival_rate"],
        deviations=result["deviations"],
        is_deviated=result["is_deviated"],
        deviation_note=(payload.deviation_note or "").strip() or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def delete_record(db: Session, record_id: int) -> None:
    record = get_record(db, record_id)
    db.delete(record)
    db.commit()
