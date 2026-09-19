"""演示数据生成：首次启动时写入，便于快速体验各模块。"""

import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    INSPECTION_CHECK_ITEMS,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomGrade,
    RestroomStatus,
    Shift,
)
from app.models import Restroom
from app.schemas.inspection import InspectionCreate, InspectionItem
from app.schemas.issue import IssueCreate, IssueStatusUpdate
from app.schemas.patrol import ActualPoint, PatrolRecordCreate, PatrolRouteCreate, RoutePoint
from app.schemas.restroom import RestroomCreate
from app.services import inspection_service, issue_service, patrol_service, restroom_service

RANDOM_SEED = 20240913

RESTROOM_SPECS = [
    ("人民广场公共厕所", "城东区", "人民广场东侧 50 米", RestroomGrade.FIRST, RestroomStatus.NORMAL, "王秀兰", 12, 6, True),
    ("滨江公园公共厕所", "城东区", "滨江公园 3 号入口", RestroomGrade.SECOND, RestroomStatus.NORMAL, "李国强", 8, 4, True),
    ("和平路公共厕所", "城东区", "和平路与解放街交叉口", RestroomGrade.THIRD, RestroomStatus.MAINTENANCE, "赵敏", 4, 2, False),
    ("火车站南广场公共厕所", "城西区", "火车站南广场西侧", RestroomGrade.FIRST, RestroomStatus.NORMAL, "陈志远", 16, 8, True),
    ("西城集贸市场公共厕所", "城西区", "西城集贸市场北门", RestroomGrade.SECOND, RestroomStatus.NORMAL, "刘桂芳", 10, 4, False),
    ("文化路步行街公共厕所", "城西区", "文化路步行街中段", RestroomGrade.SECOND, RestroomStatus.NORMAL, "孙鹏", 9, 5, True),
    ("滨江新区体育中心公共厕所", "滨江新区", "体育中心东看台下", RestroomGrade.FIRST, RestroomStatus.NORMAL, "周晓燕", 14, 7, True),
    ("滨江新区政务中心公共厕所", "滨江新区", "政务服务中心一楼", RestroomGrade.SECOND, RestroomStatus.NORMAL, "吴建华", 8, 4, True),
    ("老城隍庙公共厕所", "老城区", "城隍庙街 12 号", RestroomGrade.THIRD, RestroomStatus.NORMAL, "郑淑珍", 5, 2, False),
    ("老城区第三小学旁公共厕所", "老城区", "第三小学东侧巷道", RestroomGrade.THIRD, RestroomStatus.CLOSED, "何伟", 4, 2, False),
]

INSPECTORS = ["张伟", "刘洋", "胡明月", "邓晨曦", "马晓峰", "杨柳"]
MANAGERS = ["王秀兰", "李国强", "陈志远", "刘桂芳", "周晓燕", "吴建华", "郑淑珍", "孙鹏"]

ISSUE_TEMPLATES = {
    IssueCategory.CLEANING: [
        "地面存在明显污渍未及时清理",
        "蹲位清洁不彻底，存在残留",
        "垃圾篓内垃圾未及时清运",
    ],
    IssueCategory.FACILITY: [
        "水龙头漏水，需更换阀芯",
        "感应冲水器失灵，无法自动冲水",
        "隔间门锁损坏无法反锁",
    ],
    IssueCategory.ODOR: [
        "公厕内异味明显，通风效果差",
        "排风扇停转导致异味积聚",
    ],
    IssueCategory.CONSUMABLE: [
        "洗手液未及时补充",
        "纸巾盒空置，未补充厕纸",
    ],
    IssueCategory.SAFETY: [
        "地面湿滑未放置防滑警示牌",
        "照明灯具损坏，夜间存在安全隐患",
    ],
    IssueCategory.OTHER: [
        "无障碍扶手松动需加固",
        "标识牌褪色需更换",
    ],
}

CATEGORY_BY_ITEM = {
    "地面与台阶清洁": IssueCategory.CLEANING,
    "便池蹲位清洁": IssueCategory.CLEANING,
    "洗手台与镜面": IssueCategory.CLEANING,
    "通风除臭": IssueCategory.ODOR,
    "耗材补充": IssueCategory.CONSUMABLE,
    "垃圾清运": IssueCategory.CLEANING,
    "工具与标识摆放": IssueCategory.OTHER,
    "墙面门窗卫生": IssueCategory.CLEANING,
}

# 巡查路线演示数据：(路线名, 区域, 班次, [(RESTROOM_SPECS 下标, 计划停留分钟), ...])
ROUTE_SPECS = [
    ("城东区早班巡查线", "城东区", Shift.MORNING, [(0, 15), (1, 10), (2, 10)]),
    ("城西区中班巡查线", "城西区", Shift.MIDDLE, [(3, 20), (4, 15), (5, 15)]),
    ("滨江新区早班巡查线", "滨江新区", Shift.MORNING, [(6, 15), (7, 10)]),
    ("老城区晚班巡查线", "老城区", Shift.NIGHT, [(8, 10), (9, 10)]),
]

SHIFT_START_HOUR = {Shift.MORNING: 8, Shift.MIDDLE: 14, Shift.NIGHT: 19}

MISSED_NOTES = [
    "该点位周边道路施工围挡，绕行成本过高，已与班组长报备",
    "巡查途中接市民求助处理突发情况，该点位未能到位，次日补巡",
    "该点位临时停水封闭，现场确认无法进入，已拍照留存",
]


def _build_items(rng: random.Random, quality: float) -> list[InspectionItem]:
    items: list[InspectionItem] = []
    for name in INSPECTION_CHECK_ITEMS:
        score = quality + rng.uniform(-1.6, 1.4)
        items.append(InspectionItem(name=name, score=max(0, min(10, round(score)))))
    return items


def _pick_problem(items: list[InspectionItem]) -> str | None:
    """找出最需要整改的检查项：优先取不合格项，否则取得分最低的一项。"""
    if not items:
        return None
    problems = [item for item in items if item.score < 6]
    pool = problems or items
    return min(pool, key=lambda item: item.score).name


def seed_database(db: Session, *, reset: bool = False) -> int:
    """写入演示数据，返回新增的问题条数；已有数据时默认跳过。"""
    existing = db.scalar(select(func.count()).select_from(Restroom)) or 0
    if existing and not reset:
        return 0

    rng = random.Random(RANDOM_SEED)
    now = datetime.now()

    restrooms = [
        restroom_service.create_restroom(
            db,
            RestroomCreate(
                name=name,
                district=district,
                address=address,
                grade=grade,
                status=status,
                manager=manager,
                manager_phone=f"13{rng.randint(100000000, 999999999)}",
                stall_count=stalls,
                basin_count=basins,
                has_accessible=accessible,
                open_hours="06:00-22:30" if grade == RestroomGrade.FIRST else "06:30-21:30",
            ),
        )
        for name, district, address, grade, status, manager, stalls, basins, accessible in RESTROOM_SPECS
    ]

    quality_by_restroom = {room.id: rng.uniform(7.4, 9.8) for room in restrooms}
    inspection_ids: list[tuple[int, int]] = []  # (restroom_id, inspection_id)
    for offset in range(13, -1, -1):
        day = now - timedelta(days=offset)
        for room in restrooms:
            if room.status == RestroomStatus.CLOSED:
                continue
            if rng.random() < 0.3:
                continue
            quality = quality_by_restroom[room.id] + rng.uniform(-1.0, 0.6)
            if rng.random() < 0.18:
                quality -= 2.6
            items = _build_items(rng, quality)
            inspection = inspection_service.create_inspection(
                db,
                InspectionCreate(
                    restroom_id=room.id,
                    inspector=rng.choice(INSPECTORS),
                    shift=rng.choice(list(Shift)),
                    inspect_time=day.replace(
                        hour=rng.choice([8, 10, 14, 16, 19]), minute=rng.choice([5, 20, 35, 50])
                    ),
                    items=items,
                    remark=None,
                ),
            )
            inspection_ids.append((room.id, inspection.id))

    _seed_patrols(db, rng, now, restrooms)

    created = 0
    for restroom_id, inspection_id in inspection_ids:
        summary = inspection_service.get_inspection(db, inspection_id)
        if summary.result != "发现问题" or rng.random() > 0.75:
            continue
        problem_item = _pick_problem([InspectionItem(**item) for item in summary.items])
        category = CATEGORY_BY_ITEM.get(problem_item or "", IssueCategory.OTHER)
        title = rng.choice(ISSUE_TEMPLATES[category])
        severity = (
            IssueSeverity.URGENT
            if category in (IssueCategory.SAFETY, IssueCategory.FACILITY) and rng.random() < 0.3
            else rng.choice([IssueSeverity.NORMAL, IssueSeverity.SERIOUS])
        )
        age_days = (now - summary.inspect_time).days
        deadline = summary.inspect_time + timedelta(
            days=1 if severity == IssueSeverity.URGENT else 3
        )
        issue = issue_service.create_issue(
            db,
            IssueCreate(
                restroom_id=restroom_id,
                inspection_id=inspection_id,
                title=title,
                description=f"巡查得分 {summary.score} 分（{summary.grade}），检查项「{problem_item}」不达标，请安排整改。",
                category=category,
                severity=severity,
                reporter=summary.inspector,
                assignee=rng.choice(MANAGERS),
                deadline=deadline,
                initial_remark="由保洁巡查自动生成的问题工单",
            ),
        )
        created += 1
        _advance_issue(db, issue.id, age_days, rng)

    return created


def _advance_issue(db: Session, issue_id: int, age_days: int, rng: random.Random) -> None:
    """按问题存在时长模拟整改进度，让看板呈现多种状态。"""
    steps: list[tuple[str, str, str]] = []
    if age_days >= 1:
        steps.append(
            (
                IssueStatus.PROCESSING.value,
                "街办保洁队",
                "已派单至保洁班组，安排当日整改",
            )
        )
    if age_days >= 3:
        steps.append(
            (
                IssueStatus.REVIEWING.value,
                "整改责任人",
                "整改完成，提交巡查员验收",
            )
        )
    if age_days >= 5 and rng.random() < 0.75:
        steps.append((IssueStatus.DONE.value, "巡查员", "现场复核通过，问题已闭环"))
    if age_days >= 8 and rng.random() < 0.6:
        steps.append((IssueStatus.CLOSED.value, "值班长", "归档关闭"))

    for target, operator, remark in steps:
        try:
            issue_service.change_status(
                db,
                issue_id,
                IssueStatusUpdate(to_status=IssueStatus(target), operator=operator, remark=remark),
            )
        except Exception:  # noqa: BLE001  演示数据允许跳过不合法的流转
            break


def _seed_patrols(
    db: Session, rng: random.Random, now: datetime, restrooms: list[Restroom]
) -> None:
    """生成计划路线与近 14 天的巡查执行记录，覆盖正常与偏离样本。"""
    routes = []
    for name, district, shift, point_specs in ROUTE_SPECS:
        route = patrol_service.create_route(
            db,
            PatrolRouteCreate(
                name=name,
                district=district,
                shift=shift,
                points=[
                    RoutePoint(restroom_id=restrooms[idx].id, stay_minutes=stay)
                    for idx, stay in point_specs
                ],
                remark="按区域划分的日常巡查路线",
            ),
        )
        routes.append((route, shift, point_specs))

    for offset in range(13, -1, -1):
        day = now - timedelta(days=offset)
        for route, shift, point_specs in routes:
            if rng.random() < 0.25:
                continue
            start = day.replace(
                hour=SHIFT_START_HOUR[shift],
                minute=rng.choice([0, 5, 10, 15]),
                second=0,
                microsecond=0,
            )
            scenario = rng.random()
            skip_index = rng.randrange(len(point_specs)) if scenario < 0.15 else None
            short_index = rng.randrange(len(point_specs)) if 0.15 <= scenario < 0.28 else None
            reversed_order = 0.28 <= scenario < 0.36 and len(point_specs) > 1
            with_extra = 0.36 <= scenario < 0.44

            visit_indexes = list(range(len(point_specs)))
            if reversed_order:
                visit_indexes.reverse()

            actual_points: list[ActualPoint] = []
            cursor = start
            for idx in visit_indexes:
                if idx == skip_index:
                    continue
                _, planned_stay = point_specs[idx]
                cursor = cursor + timedelta(minutes=rng.randint(8, 18))
                arrive = cursor
                stay = planned_stay
                if idx == short_index:
                    stay = max(1, planned_stay - rng.randint(3, 6))
                else:
                    stay = max(1, planned_stay + rng.randint(-2, 4))
                leave = arrive + timedelta(minutes=stay)
                actual_points.append(
                    ActualPoint(
                        restroom_id=route.points[idx]["restroom_id"],
                        arrive_at=arrive,
                        leave_at=leave,
                    )
                )
                cursor = leave

            if with_extra:
                planned_ids = {p["restroom_id"] for p in route.points}
                candidates = [room for room in restrooms if room.id not in planned_ids]
                if candidates:
                    extra = rng.choice(candidates)
                    arrive = cursor + timedelta(minutes=rng.randint(8, 15))
                    actual_points.append(
                        ActualPoint(
                            restroom_id=extra.id,
                            arrive_at=arrive,
                            leave_at=arrive + timedelta(minutes=rng.randint(4, 10)),
                        )
                    )
                    cursor = actual_points[-1].leave_at

            if not actual_points:
                continue
            end = cursor + timedelta(minutes=rng.randint(2, 8))
            note = rng.choice(MISSED_NOTES) if skip_index is not None else None
            patrol_service.create_record(
                db,
                PatrolRecordCreate(
                    route_id=route.id,
                    inspector=rng.choice(INSPECTORS),
                    start_time=start,
                    end_time=end,
                    actual_points=actual_points,
                    deviation_note=note,
                ),
            )
