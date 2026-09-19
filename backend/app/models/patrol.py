"""巡查路线与巡查执行记录模型。"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import Shift
from app.core.database import Base


class PatrolRoute(Base):
    """计划巡查路线：一组有序的公厕点位及计划停留时长。"""

    __tablename__ = "patrol_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, comment="路线名称")
    district: Mapped[str] = mapped_column(String(60), index=True, comment="所属区域")
    shift: Mapped[str] = mapped_column(String(20), default=Shift.MORNING.value, comment="班次")
    points: Mapped[list[dict]] = mapped_column(
        JSON, default=list, comment="计划点位：[{restroom_id, stay_minutes}]，顺序即巡查顺序"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    records: Mapped[list["PatrolRecord"]] = relationship(
        back_populates="route", cascade="all, delete-orphan"
    )


class PatrolRecord(Base):
    """一次巡查执行的路线记录，含实际轨迹与计划比对结果。"""

    __tablename__ = "patrol_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("patrol_routes.id", ondelete="CASCADE"), index=True, comment="计划路线"
    )
    inspector: Mapped[str] = mapped_column(String(60), index=True, comment="巡查人")
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True, comment="巡查开始时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, comment="巡查结束时间")
    actual_points: Mapped[list[dict]] = mapped_column(
        JSON,
        default=list,
        comment="实际轨迹：[{restroom_id, point_name, arrive_at, leave_at}]",
    )
    planned_count: Mapped[int] = mapped_column(Integer, default=0, comment="计划点位数")
    arrived_count: Mapped[int] = mapped_column(Integer, default=0, comment="实际到点位数")
    arrival_rate: Mapped[float] = mapped_column(Float, default=0.0, comment="到位率（%）")
    deviations: Mapped[list[dict]] = mapped_column(
        JSON, default=list, comment="偏离明细：[{type, restroom_id, point_name, detail}]"
    )
    is_deviated: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, comment="是否偏离明显"
    )
    deviation_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="偏离说明（偏离明显时必填）"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    route: Mapped["PatrolRoute"] = relationship(back_populates="records")
