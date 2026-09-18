"""巡查路线相关数据结构：计划路线与巡查执行记录。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import Shift


class PatrolPlanPoint(BaseModel):
    """计划路线上的一个点位。"""

    restroom_id: int = Field(description="公厕 ID")
    stay_minutes: int = Field(default=15, ge=1, le=240, description="计划停留时长（分钟）")


class PatrolPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="路线名称")
    district: str = Field(min_length=1, max_length=60, description="所属区域")
    inspector: str = Field(min_length=1, max_length=60, description="计划巡查人")
    shift: Shift = Field(default=Shift.MORNING, description="班次")
    points: list[PatrolPlanPoint] = Field(min_length=1, description="计划点位，按顺序到访")
    remark: str | None = Field(default=None, max_length=500)


class PatrolPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    district: str | None = Field(default=None, min_length=1, max_length=60)
    inspector: str | None = Field(default=None, min_length=1, max_length=60)
    shift: Shift | None = None
    points: list[PatrolPlanPoint] | None = Field(default=None, min_length=1)
    remark: str | None = Field(default=None, max_length=500)


class PatrolPointRef(BaseModel):
    """点位引用，附带解析后的公厕名称。"""

    restroom_id: int
    restroom_name: str
    restroom_code: str = ""


class PatrolPlanPointOut(PatrolPointRef):
    stay_minutes: int


class PatrolPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    district: str
    inspector: str
    shift: str
    points: list[PatrolPlanPointOut] = Field(default_factory=list)
    remark: str | None = None
    record_count: int = 0
    created_at: datetime


class PatrolTrackPoint(BaseModel):
    """实际轨迹中的一个点位：到达与离开时间用于计算停留时长。"""

    restroom_id: int = Field(description="公厕 ID")
    arrive_time: datetime = Field(description="到达时间")
    leave_time: datetime = Field(description="离开时间")


class PatrolRecordCreate(BaseModel):
    plan_id: int = Field(description="所属计划路线 ID")
    inspector: str = Field(min_length=1, max_length=60, description="实际巡查人")
    start_time: datetime = Field(description="巡查开始时间")
    end_time: datetime = Field(description="巡查结束时间")
    tracks: list[PatrolTrackPoint] = Field(min_length=1, description="实际经过的点位轨迹")
    deviation_note: str | None = Field(
        default=None, max_length=500, description="偏离补充说明，明显偏离时必填"
    )
    remark: str | None = Field(default=None, max_length=500)


class PatrolRecordUpdate(BaseModel):
    inspector: str | None = Field(default=None, min_length=1, max_length=60)
    start_time: datetime | None = None
    end_time: datetime | None = None
    tracks: list[PatrolTrackPoint] | None = Field(default=None, min_length=1)
    deviation_note: str | None = Field(default=None, max_length=500)
    remark: str | None = Field(default=None, max_length=500)


class PatrolTrackOut(PatrolPointRef):
    arrive_time: datetime
    leave_time: datetime
    stay_minutes: float = Field(description="停留时长（分钟）")


class PatrolDeviationOut(BaseModel):
    """巡查记录与计划路线的比对结果。"""

    missed: list[PatrolPointRef] = Field(default_factory=list, description="漏巡点位")
    extra: list[PatrolPointRef] = Field(default_factory=list, description="计划外点位")
    out_of_order: bool = Field(default=False, description="到访顺序与计划不一致")


class PatrolRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    plan_name: str = ""
    inspector: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float = Field(default=0.0, description="巡查总时长（分钟）")
    tracks: list[PatrolTrackOut] = Field(default_factory=list)
    arrival_rate: float = Field(description="到位率（百分比）")
    deviation_level: str
    deviation: PatrolDeviationOut = Field(default_factory=PatrolDeviationOut)
    deviation_note: str | None = None
    remark: str | None = None
    created_at: datetime
