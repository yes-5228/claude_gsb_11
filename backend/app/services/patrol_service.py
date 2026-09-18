"""巡查路线业务逻辑：计划路线管理与巡查执行的路线比对。"""

from datetime import date, datetime, time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    PATROL_ARRIVAL_RATE_SIGNIFICANT_THRESHOLD,
    PATROL_MISSED_SIGNIFICANT_THRESHOLD,
    PatrolDeviationLevel,
)
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models import PatrolPlan, PatrolRecord, Restroom
from app.schemas.patrol import (
    PatrolDeviationOut,
    PatrolPlanCreate,
    PatrolPlanOut,
    PatrolPlanPointOut,
    PatrolPlanUpdate,
    PatrolPointRef,
    PatrolRecordCreate,
    PatrolRecordOut,
    PatrolRecordUpdate,
    PatrolTrackOut,
)

PLAN_SORTABLE_FIELDS = {
    "created_at": PatrolPlan.created_at,
    "name": PatrolPlan.name,
}

RECORD_SORTABLE_FIELDS = {
    "start_time": PatrolRecord.start_time,
    "arrival_rate": PatrolRecord.arrival_rate,
    "created_at": PatrolRecord.created_at,
}


# ---------------------------------------------------------------------------
# 数据规整与校验
# ---------------------------------------------------------------------------


def _normalize_points(points: list) -> list[dict]:
    seen: set[int] = set()
    normalized: list[dict] = []
    for point in points:
        data = point.model_dump() if hasattr(point, "model_dump") else dict(point)
        restroom_id = int(data.get("restroom_id") or 0)
        if restroom_id in seen:
            raise DomainError(f"点位公厕 {restroom_id} 在路线中重复")
        seen.add(restroom_id)
        normalized.append(
            {"restroom_id": restroom_id, "stay_minutes": int(data.get("stay_minutes") or 15)}
        )
    if not normalized:
        raise DomainError("计划路线至少需要一个点位")
    return normalized


def _as_datetime(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _normalize_tracks(tracks: list, start_time: datetime, end_time: datetime) -> list[dict]:
    if end_time <= start_time:
        raise DomainError("巡查结束时间必须晚于开始时间")
    seen: set[int] = set()
    normalized: list[dict] = []
    for track in tracks:
        data = track.model_dump() if hasattr(track, "model_dump") else dict(track)
        restroom_id = int(data.get("restroom_id") or 0)
        if restroom_id in seen:
            raise DomainError(f"轨迹中公厕 {restroom_id} 重复出现")
        seen.add(restroom_id)
        arrive = _as_datetime(data.get("arrive_time"))
        leave = _as_datetime(data.get("leave_time"))
        if arrive is None or leave is None:
            raise DomainError("轨迹点位需包含到达与离开时间")
        if leave < arrive:
            raise DomainError("轨迹点位的离开时间不能早于到达时间")
        if arrive < start_time or leave > end_time:
            raise DomainError("轨迹点位的到离时间需位于巡查起止时间内")
        stay = round((leave - arrive).total_seconds() / 60, 1)
        normalized.append(
            {
                "restroom_id": restroom_id,
                "arrive_time": arrive.isoformat(),
                "leave_time": leave.isoformat(),
                "stay_minutes": stay,
            }
        )
    if not normalized:
        raise DomainError("巡查轨迹至少需要一个点位")
    normalized.sort(key=lambda item: item["arrive_time"])
    return normalized


def _ensure_restrooms_exist(db: Session, restroom_ids: list[int]) -> None:
    if not restroom_ids:
        return
    found = set(
        db.scalars(select(Restroom.id).where(Restroom.id.in_(restroom_ids))).all()
    )
    missing = [str(rid) for rid in restroom_ids if rid not in found]
    if missing:
        raise DomainError(f"点位公厕不存在：{', '.join(missing)}")


# ---------------------------------------------------------------------------
# 路线比对：到位率与偏离情况
# ---------------------------------------------------------------------------


def compare_route(plan_points: list[dict], tracks: list[dict]) -> tuple[float, str, dict]:
    """比对计划路线与实际轨迹，返回 (到位率, 偏离程度, 偏离明细)。

    - 到位率 = 实际到访的计划点位数 / 计划点位总数 × 100
    - 无偏离：无漏巡、无计划外点位且顺序一致
    - 明显偏离：到位率低于阈值或漏巡点位达到阈值
    - 其余为轻微偏离
    """
    planned_ids = [int(point["restroom_id"]) for point in plan_points]
    actual_ids = [int(track["restroom_id"]) for track in tracks]
    planned_set = set(planned_ids)
    actual_set = set(actual_ids)

    missed = [rid for rid in planned_ids if rid not in actual_set]
    extra = [rid for rid in actual_ids if rid not in planned_set]
    # 顺序偏离：实际到访的计划内点位，其相对顺序与计划顺序不一致
    planned_sequence = [rid for rid in planned_ids if rid in actual_set]
    actual_sequence = [rid for rid in actual_ids if rid in planned_set]
    out_of_order = planned_sequence != actual_sequence

    arrival_rate = (
        round(len(planned_set & actual_set) / len(planned_ids) * 100, 1) if planned_ids else 0.0
    )

    if not missed and not extra and not out_of_order:
        level = PatrolDeviationLevel.NONE.value
    elif arrival_rate < PATROL_ARRIVAL_RATE_SIGNIFICANT_THRESHOLD or (
        len(missed) >= PATROL_MISSED_SIGNIFICANT_THRESHOLD
    ):
        level = PatrolDeviationLevel.SIGNIFICANT.value
    else:
        level = PatrolDeviationLevel.MINOR.value

    detail = {"missed": missed, "extra": extra, "out_of_order": out_of_order}
    return arrival_rate, level, detail


def _require_note_if_significant(level: str, deviation_note: str | None) -> None:
    if level == PatrolDeviationLevel.SIGNIFICANT.value and not (deviation_note or "").strip():
        raise DomainError("本次巡查与计划路线偏离明显，需补充偏离说明")


# ---------------------------------------------------------------------------
# 输出组装：解析点位名称
# ---------------------------------------------------------------------------


def _restroom_refs(db: Session, restroom_ids: list[int]) -> dict[int, PatrolPointRef]:
    unique_ids = list(dict.fromkeys(int(rid) for rid in restroom_ids))
    refs: dict[int, PatrolPointRef] = {}
    if unique_ids:
        rows = db.scalars(select(Restroom).where(Restroom.id.in_(unique_ids))).all()
        for row in rows:
            refs[row.id] = PatrolPointRef(
                restroom_id=row.id, restroom_name=row.name, restroom_code=row.code
            )
    for rid in unique_ids:
        refs.setdefault(rid, PatrolPointRef(restroom_id=rid, restroom_name=f"公厕#{rid}"))
    return refs


def to_plan_out(db: Session, plan: PatrolPlan) -> PatrolPlanOut:
    refs = _restroom_refs(db, [point["restroom_id"] for point in plan.points or []])
    return PatrolPlanOut(
        id=plan.id,
        name=plan.name,
        district=plan.district,
        inspector=plan.inspector,
        shift=plan.shift,
        points=[
            PatrolPlanPointOut(
                **refs[int(point["restroom_id"])].model_dump(),
                stay_minutes=int(point.get("stay_minutes") or 0),
            )
            for point in plan.points or []
        ],
        remark=plan.remark,
        record_count=len(plan.records),
        created_at=plan.created_at,
    )


def to_record_out(db: Session, record: PatrolRecord) -> PatrolRecordOut:
    detail = record.deviation_detail or {}
    track_ids = [track["restroom_id"] for track in record.tracks or []]
    all_ids = track_ids + list(detail.get("missed", [])) + list(detail.get("extra", []))
    refs = _restroom_refs(db, all_ids)

    return PatrolRecordOut(
        id=record.id,
        plan_id=record.plan_id,
        plan_name=record.plan.name if record.plan else "",
        inspector=record.inspector,
        start_time=record.start_time,
        end_time=record.end_time,
        duration_minutes=round((record.end_time - record.start_time).total_seconds() / 60, 1),
        tracks=[
            PatrolTrackOut(
                **refs[int(track["restroom_id"])].model_dump(),
                arrive_time=datetime.fromisoformat(str(track["arrive_time"])),
                leave_time=datetime.fromisoformat(str(track["leave_time"])),
                stay_minutes=float(track.get("stay_minutes") or 0),
            )
            for track in record.tracks or []
        ],
        arrival_rate=record.arrival_rate,
        deviation_level=record.deviation_level,
        deviation=PatrolDeviationOut(
            missed=[refs[int(rid)] for rid in detail.get("missed", [])],
            extra=[refs[int(rid)] for rid in detail.get("extra", [])],
            out_of_order=bool(detail.get("out_of_order")),
        ),
        deviation_note=record.deviation_note,
        remark=record.remark,
        created_at=record.created_at,
    )


# ---------------------------------------------------------------------------
# 计划路线 CRUD
# ---------------------------------------------------------------------------


def get_plan(db: Session, plan_id: int) -> PatrolPlan:
    plan = db.get(PatrolPlan, plan_id)
    if plan is None:
        raise NotFoundError(f"计划路线 {plan_id} 不存在")
    return plan


def list_plans(
    db: Session,
    *,
    district: str | None = None,
    inspector: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "created_at",
    order: str = "desc",
) -> tuple[list[PatrolPlan], int]:
    stmt = select(PatrolPlan)
    if district:
        stmt = stmt.where(PatrolPlan.district == district)
    if inspector:
        stmt = stmt.where(PatrolPlan.inspector.like(f"%{inspector.strip()}%"))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(PatrolPlan.name.like(like), PatrolPlan.remark.like(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = PLAN_SORTABLE_FIELDS.get(sort_by, PatrolPlan.created_at)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), PatrolPlan.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def create_plan(db: Session, payload: PatrolPlanCreate) -> PatrolPlan:
    points = _normalize_points(payload.points)
    _ensure_restrooms_exist(db, [point["restroom_id"] for point in points])
    plan = PatrolPlan(
        name=payload.name.strip(),
        district=payload.district.strip(),
        inspector=payload.inspector.strip(),
        shift=payload.shift.value if hasattr(payload.shift, "value") else payload.shift,
        points=points,
        remark=payload.remark,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(db: Session, plan_id: int, payload: PatrolPlanUpdate) -> PatrolPlan:
    plan = get_plan(db, plan_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("points") is not None:
        points = _normalize_points(payload.points or [])
        _ensure_restrooms_exist(db, [point["restroom_id"] for point in points])
        plan.points = points
    if data.get("name"):
        plan.name = payload.name.strip()
    if data.get("district"):
        plan.district = payload.district.strip()
    if data.get("inspector"):
        plan.inspector = payload.inspector.strip()
    if data.get("shift") is not None and payload.shift is not None:
        plan.shift = payload.shift.value if hasattr(payload.shift, "value") else payload.shift
    if "remark" in data:
        plan.remark = payload.remark
    db.commit()
    db.refresh(plan)
    return plan


def delete_plan(db: Session, plan_id: int, *, force: bool = False) -> None:
    plan = get_plan(db, plan_id)
    if plan.records and not force:
        raise ConflictError(f"该路线已产生 {len(plan.records)} 条巡查记录，无法直接删除")
    db.delete(plan)
    db.commit()


# ---------------------------------------------------------------------------
# 巡查执行记录 CRUD
# ---------------------------------------------------------------------------


def get_record(db: Session, record_id: int) -> PatrolRecord:
    record = db.get(PatrolRecord, record_id)
    if record is None:
        raise NotFoundError(f"巡查路线记录 {record_id} 不存在")
    return record


def list_records(
    db: Session,
    *,
    plan_id: int | None = None,
    inspector: str | None = None,
    deviation_level: str | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "start_time",
    order: str = "desc",
) -> tuple[list[PatrolRecord], int]:
    stmt = select(PatrolRecord)
    if plan_id:
        stmt = stmt.where(PatrolRecord.plan_id == plan_id)
    if inspector:
        stmt = stmt.where(PatrolRecord.inspector.like(f"%{inspector.strip()}%"))
    if deviation_level:
        stmt = stmt.where(PatrolRecord.deviation_level == deviation_level)
    if date_from:
        stmt = stmt.where(PatrolRecord.start_time >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(PatrolRecord.start_time <= datetime.combine(date_to, time.max))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                PatrolRecord.inspector.like(like),
                PatrolRecord.remark.like(like),
                PatrolRecord.deviation_note.like(like),
                PatrolRecord.plan_id.in_(select(PatrolPlan.id).where(PatrolPlan.name.like(like))),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = RECORD_SORTABLE_FIELDS.get(sort_by, PatrolRecord.start_time)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), PatrolRecord.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def create_record(db: Session, payload: PatrolRecordCreate) -> PatrolRecord:
    plan = get_plan(db, payload.plan_id)
    tracks = _normalize_tracks(payload.tracks, payload.start_time, payload.end_time)
    _ensure_restrooms_exist(db, [track["restroom_id"] for track in tracks])
    arrival_rate, level, detail = compare_route(plan.points or [], tracks)
    _require_note_if_significant(level, payload.deviation_note)
    record = PatrolRecord(
        plan_id=plan.id,
        inspector=payload.inspector.strip(),
        start_time=payload.start_time,
        end_time=payload.end_time,
        tracks=tracks,
        arrival_rate=arrival_rate,
        deviation_level=level,
        deviation_detail=detail,
        deviation_note=(payload.deviation_note or "").strip() or None,
        remark=payload.remark,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_record(db: Session, record_id: int, payload: PatrolRecordUpdate) -> PatrolRecord:
    record = get_record(db, record_id)
    data = payload.model_dump(exclude_unset=True)

    start_time = payload.start_time or record.start_time
    end_time = payload.end_time or record.end_time
    if data.get("tracks") is not None:
        tracks = _normalize_tracks(payload.tracks or [], start_time, end_time)
    else:
        # 未提交新轨迹时，用既有轨迹按新起止时间重新校验并计算停留时长
        tracks = _normalize_tracks(record.tracks or [], start_time, end_time)
    _ensure_restrooms_exist(db, [track["restroom_id"] for track in tracks])

    arrival_rate, level, detail = compare_route(record.plan.points or [], tracks)
    note = payload.deviation_note if "deviation_note" in data else record.deviation_note
    _require_note_if_significant(level, note)

    if data.get("inspector"):
        record.inspector = payload.inspector.strip()
    record.start_time = start_time
    record.end_time = end_time
    record.tracks = tracks
    record.arrival_rate = arrival_rate
    record.deviation_level = level
    record.deviation_detail = detail
    if "deviation_note" in data:
        record.deviation_note = (payload.deviation_note or "").strip() or None
    if "remark" in data:
        record.remark = payload.remark
    db.commit()
    db.refresh(record)
    return record


def delete_record(db: Session, record_id: int) -> None:
    record = get_record(db, record_id)
    db.delete(record)
    db.commit()
