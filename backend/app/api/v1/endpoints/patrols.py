"""巡查路线接口：计划路线与巡查执行记录。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep, build_meta
from app.core.database import get_db
from app.schemas.common import MessageOut, Page
from app.schemas.patrol import (
    PatrolPlanCreate,
    PatrolPlanOut,
    PatrolPlanUpdate,
    PatrolRecordCreate,
    PatrolRecordOut,
    PatrolRecordUpdate,
)
from app.services import patrol_service

plan_router = APIRouter(prefix="/patrol-plans", tags=["巡查路线"])
record_router = APIRouter(prefix="/patrol-records", tags=["巡查路线"])


# ---------------------------------------------------------------------------
# 计划路线
# ---------------------------------------------------------------------------


@plan_router.get("", response_model=Page[PatrolPlanOut], summary="计划路线列表")
def list_plans(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    district: Annotated[str | None, Query(description="按区域过滤")] = None,
    inspector: Annotated[str | None, Query(description="计划巡查人")] = None,
    keyword: Annotated[str | None, Query(description="路线名称/备注模糊搜索")] = None,
    sort_by: Annotated[str, Query(description="排序字段")] = "created_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[PatrolPlanOut]:
    rows, total = patrol_service.list_plans(
        db,
        district=district,
        inspector=inspector,
        keyword=keyword,
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        order=order,
    )
    return Page[PatrolPlanOut](
        items=[patrol_service.to_plan_out(db, row) for row in rows],
        meta=build_meta(total, pagination),
    )


@plan_router.post("", response_model=PatrolPlanOut, status_code=201, summary="新增计划路线")
def create_plan(
    payload: PatrolPlanCreate, db: Annotated[Session, Depends(get_db)]
) -> PatrolPlanOut:
    return patrol_service.to_plan_out(db, patrol_service.create_plan(db, payload))


@plan_router.get("/{plan_id}", response_model=PatrolPlanOut, summary="计划路线详情")
def get_plan(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> PatrolPlanOut:
    return patrol_service.to_plan_out(db, patrol_service.get_plan(db, plan_id))


@plan_router.patch("/{plan_id}", response_model=PatrolPlanOut, summary="更新计划路线")
def update_plan(
    plan_id: int, payload: PatrolPlanUpdate, db: Annotated[Session, Depends(get_db)]
) -> PatrolPlanOut:
    return patrol_service.to_plan_out(db, patrol_service.update_plan(db, plan_id, payload))


@plan_router.delete("/{plan_id}", response_model=MessageOut, summary="删除计划路线")
def delete_plan(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query(description="存在巡查记录时强制级联删除")] = False,
) -> MessageOut:
    patrol_service.delete_plan(db, plan_id, force=force)
    return MessageOut(message="删除成功")


# ---------------------------------------------------------------------------
# 巡查执行记录
# ---------------------------------------------------------------------------


@record_router.get("", response_model=Page[PatrolRecordOut], summary="巡查路线记录列表")
def list_records(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    plan_id: Annotated[int | None, Query(description="按计划路线过滤")] = None,
    inspector: Annotated[str | None, Query(description="巡查人")] = None,
    deviation_level: Annotated[str | None, Query(description="偏离程度")] = None,
    keyword: Annotated[str | None, Query(description="路线名称/巡查人/说明模糊搜索")] = None,
    date_from: Annotated[date | None, Query(description="开始日期")] = None,
    date_to: Annotated[date | None, Query(description="结束日期")] = None,
    sort_by: Annotated[str, Query(description="排序字段")] = "start_time",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[PatrolRecordOut]:
    rows, total = patrol_service.list_records(
        db,
        plan_id=plan_id,
        inspector=inspector,
        deviation_level=deviation_level,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        order=order,
    )
    return Page[PatrolRecordOut](
        items=[patrol_service.to_record_out(db, row) for row in rows],
        meta=build_meta(total, pagination),
    )


@record_router.post("", response_model=PatrolRecordOut, status_code=201, summary="新增巡查路线记录")
def create_record(
    payload: PatrolRecordCreate, db: Annotated[Session, Depends(get_db)]
) -> PatrolRecordOut:
    return patrol_service.to_record_out(db, patrol_service.create_record(db, payload))


@record_router.get("/{record_id}", response_model=PatrolRecordOut, summary="巡查路线记录详情")
def get_record(record_id: int, db: Annotated[Session, Depends(get_db)]) -> PatrolRecordOut:
    return patrol_service.to_record_out(db, patrol_service.get_record(db, record_id))


@record_router.patch("/{record_id}", response_model=PatrolRecordOut, summary="更新巡查路线记录")
def update_record(
    record_id: int, payload: PatrolRecordUpdate, db: Annotated[Session, Depends(get_db)]
) -> PatrolRecordOut:
    return patrol_service.to_record_out(db, patrol_service.update_record(db, record_id, payload))


@record_router.delete("/{record_id}", response_model=MessageOut, summary="删除巡查路线记录")
def delete_record(record_id: int, db: Annotated[Session, Depends(get_db)]) -> MessageOut:
    patrol_service.delete_record(db, record_id)
    return MessageOut(message="删除成功")
