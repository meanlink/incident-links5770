from sqlalchemy import String, JSON, Double, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Dataset(Base):
    __tablename__ = 'datasets'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    records: Mapped[list] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Double)
    # 增量接入台账：基线批次 root_id 指向自身；派生批次指向最初批次
    root_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    # 当前有效（未撤销、取最高版本）事件快照，analyze 仍只消费 records，旧批次字段永不回写
    effective_records: Mapped[list | None] = mapped_column(JSON, nullable=True)
    effective_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 最近一次增量批次统计（新增/更正/撤销/忽略/冲突）
    last_ingest_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
