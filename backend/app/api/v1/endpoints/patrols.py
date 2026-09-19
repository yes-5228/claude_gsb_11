"""巡查路线计划与巡查执行记录接口。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep, build_meta
from app.core.database import get_db
from app.schemas.common import MessageOut, Page
from app.schemas.patrol import (
    PatrolRecordCreate,
    PatrolRecordOut,
    PatrolRouteCreate,
    PatrolRouteOut,
    PatrolRouteUpdate,
)
from app.services import patrol_service

router = APIRouter(tags=["巡查路线"])


# ---------------------------------------------------------------- 路线计划


@router.get("/patrol-routes", response_model=list[PatrolRouteOut], summary="巡查路线列表")
def list_routes(
    db: Annotated[Session, Depends(get_db)],
    district: Annotated[str | None, Query(description="按区域过滤")] = None,
    shift: Annotated[str | None, Query(description="按班次过滤")] = None,
    enabled: Annotated[bool | None, Query(description="按启用状态过滤")] = None,
    keyword: Annotated[str | None, Query(description="路线名称/备注模糊搜索")] = None,
) -> list[PatrolRouteOut]:
    rows = patrol_service.list_routes(
        db, district=district, shift=shift, enabled=enabled, keyword=keyword
    )
    return [patrol_service.route_to_out(db, row) for row in rows]


@router.post("/patrol-routes", response_model=PatrolRouteOut, status_code=201, summary="新增巡查路线")
def create_route(
    payload: PatrolRouteCreate, db: Annotated[Session, Depends(get_db)]
) -> PatrolRouteOut:
    return patrol_service.route_to_out(db, patrol_service.create_route(db, payload))


@router.get("/patrol-routes/{route_id}", response_model=PatrolRouteOut, summary="巡查路线详情")
def get_route(route_id: int, db: Annotated[Session, Depends(get_db)]) -> PatrolRouteOut:
    return patrol_service.route_to_out(db, patrol_service.get_route(db, route_id))


@router.patch("/patrol-routes/{route_id}", response_model=PatrolRouteOut, summary="更新巡查路线")
def update_route(
    route_id: int, payload: PatrolRouteUpdate, db: Annotated[Session, Depends(get_db)]
) -> PatrolRouteOut:
    return patrol_service.route_to_out(db, patrol_service.update_route(db, route_id, payload))


@router.delete("/patrol-routes/{route_id}", response_model=MessageOut, summary="删除巡查路线")
def delete_route(
    route_id: int,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query(description="有巡查记录时强制级联删除")] = False,
) -> MessageOut:
    patrol_service.delete_route(db, route_id, force=force)
    return MessageOut(message="删除成功")


# ---------------------------------------------------------------- 执行记录


@router.get("/patrol-records", response_model=Page[PatrolRecordOut], summary="巡查执行记录列表")
def list_records(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    route_id: Annotated[int | None, Query(description="按路线过滤")] = None,
    district: Annotated[str | None, Query(description="按区域过滤")] = None,
    inspector: Annotated[str | None, Query(description="巡查人")] = None,
    is_deviated: Annotated[bool | None, Query(description="是否偏离明显")] = None,
    keyword: Annotated[str | None, Query(description="路线名称/巡查人/偏离说明模糊搜索")] = None,
    date_from: Annotated[date | None, Query(description="开始日期")] = None,
    date_to: Annotated[date | None, Query(description="结束日期")] = None,
    sort_by: Annotated[str, Query(description="排序字段")] = "start_time",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[PatrolRecordOut]:
    rows, total = patrol_service.list_records(
        db,
        route_id=route_id,
        district=district,
        inspector=inspector,
        is_deviated=is_deviated,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        order=order,
    )
    return Page[PatrolRecordOut](
        items=[patrol_service.record_to_out(row) for row in rows],
        meta=build_meta(total, pagination),
    )


@router.post(
    "/patrol-records", response_model=PatrolRecordOut, status_code=201, summary="登记巡查执行记录"
)
def create_record(
    payload: PatrolRecordCreate, db: Annotated[Session, Depends(get_db)]
) -> PatrolRecordOut:
    return patrol_service.record_to_out(patrol_service.create_record(db, payload))


@router.get("/patrol-records/{record_id}", response_model=PatrolRecordOut, summary="巡查执行记录详情")
def get_record(record_id: int, db: Annotated[Session, Depends(get_db)]) -> PatrolRecordOut:
    return patrol_service.record_to_out(patrol_service.get_record(db, record_id))


@router.delete("/patrol-records/{record_id}", response_model=MessageOut, summary="删除巡查执行记录")
def delete_record(record_id: int, db: Annotated[Session, Depends(get_db)]) -> MessageOut:
    patrol_service.delete_record(db, record_id)
    return MessageOut(message="删除成功")
