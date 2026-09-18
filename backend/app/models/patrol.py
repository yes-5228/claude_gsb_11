"""巡查路线模型：计划路线与巡查执行记录。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PatrolDeviationLevel, Shift
from app.core.database import Base


class PatrolPlan(Base):
    """计划巡查路线：一组按顺序到访的公厕点位。"""

    __tablename__ = "patrol_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, comment="路线名称")
    district: Mapped[str] = mapped_column(String(60), index=True, comment="所属区域")
    inspector: Mapped[str] = mapped_column(String(60), comment="计划巡查人")
    shift: Mapped[str] = mapped_column(String(20), default=Shift.MORNING.value, comment="班次")
    points: Mapped[list[dict]] = mapped_column(
        JSON, default=list, comment="计划点位：[{restroom_id, stay_minutes}]，按顺序到访"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    records: Mapped[list["PatrolRecord"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PatrolRecord(Base):
    """一次巡查执行的路线记录，比对结果在写入时快照保存，保证可追溯。"""

    __tablename__ = "patrol_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("patrol_plans.id", ondelete="CASCADE"), index=True, comment="所属计划路线"
    )
    inspector: Mapped[str] = mapped_column(String(60), index=True, comment="实际巡查人")
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True, comment="巡查开始时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, comment="巡查结束时间")
    tracks: Mapped[list[dict]] = mapped_column(
        JSON,
        default=list,
        comment="实际轨迹：[{restroom_id, arrive_time, leave_time, stay_minutes}]，按到达时间排序",
    )
    arrival_rate: Mapped[float] = mapped_column(Float, default=0.0, comment="到位率（百分比）")
    deviation_level: Mapped[str] = mapped_column(
        String(20), default=PatrolDeviationLevel.NONE.value, index=True, comment="偏离程度"
    )
    deviation_detail: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="偏离明细：{missed, extra, out_of_order}"
    )
    deviation_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="偏离补充说明（明显偏离时必填）"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    plan: Mapped["PatrolPlan"] = relationship(back_populates="records")
