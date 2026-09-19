"""巡查路线与执行记录相关数据结构。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import Shift


class RoutePoint(BaseModel):
    """计划路线上的一个点位。"""

    restroom_id: int = Field(description="公厕 ID")
    stay_minutes: int = Field(ge=1, le=120, description="计划停留时长（分钟）")


class PatrolRouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="路线名称")
    district: str = Field(min_length=1, max_length=60, description="所属区域")
    shift: Shift = Field(default=Shift.MORNING, description="班次")
    points: list[RoutePoint] = Field(min_length=1, description="计划点位（按巡查顺序）")
    enabled: bool = Field(default=True, description="是否启用")
    remark: str | None = Field(default=None, max_length=500)


class PatrolRouteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    district: str | None = Field(default=None, min_length=1, max_length=60)
    shift: Shift | None = None
    points: list[RoutePoint] | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    remark: str | None = Field(default=None, max_length=500)


class RoutePointOut(BaseModel):
    """带出参用的计划点位，附带公厕名称快照。"""

    restroom_id: int
    restroom_name: str = ""
    restroom_code: str = ""
    stay_minutes: int


class PatrolRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    district: str
    shift: str
    points: list[RoutePointOut] = Field(default_factory=list)
    enabled: bool
    remark: str | None = None
    record_count: int = 0
    created_at: datetime


class ActualPoint(BaseModel):
    """实际巡查经过的一个点位。"""

    restroom_id: int = Field(description="公厕 ID")
    arrive_at: datetime = Field(description="到达时间")
    leave_at: datetime = Field(description="离开时间")

    @model_validator(mode="after")
    def check_time_order(self) -> "ActualPoint":
        if self.leave_at < self.arrive_at:
            raise ValueError("离开时间不能早于到达时间")
        return self


class PatrolRecordCreate(BaseModel):
    route_id: int
    inspector: str = Field(min_length=1, max_length=60, description="巡查人")
    start_time: datetime = Field(description="巡查开始时间")
    end_time: datetime = Field(description="巡查结束时间")
    actual_points: list[ActualPoint] = Field(default_factory=list, description="实际经过点位")
    deviation_note: str | None = Field(default=None, max_length=500, description="偏离说明")

    @model_validator(mode="after")
    def check_time_order(self) -> "PatrolRecordCreate":
        if self.end_time < self.start_time:
            raise ValueError("结束时间不能早于开始时间")
        return self


class DeviationItem(BaseModel):
    """一条偏离明细。"""

    type: str = Field(description="偏离类型")
    restroom_id: int | None = None
    point_name: str = ""
    detail: str = ""


class ActualPointOut(BaseModel):
    """实际点位出参，附带名称与停留时长。"""

    restroom_id: int
    point_name: str = ""
    arrive_at: datetime
    leave_at: datetime
    stay_minutes: int = 0
    planned: bool = True


class PatrolRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    route_name: str = ""
    inspector: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int = 0
    actual_points: list[ActualPointOut] = Field(default_factory=list)
    planned_count: int
    arrived_count: int
    arrival_rate: float
    deviations: list[DeviationItem] = Field(default_factory=list)
    is_deviated: bool
    deviation_note: str | None = None
    created_at: datetime
