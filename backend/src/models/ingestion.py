from sqlalchemy import String, JSON, Double, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class IngestBatch(Base):
    """一次增量接入批次：挂在批次链根上，自身不可变。

    dataset_id 为链路根批次（版本台账的归属），derived_dataset_id 为本次合并生成的派生批次。
    """
    __tablename__ = 'ingest_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), index=True)
    derived_dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    source: Mapped[str] = mapped_column(String(200), default='supplement.json')
    # 接入前的基线快照指纹，便于追溯该批次基于哪一版事件合并
    base_checksum: Mapped[str] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(64))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Double)


class EventJournal(Base):
    """事件版本台账：每个 event_id + version 一行，撤销以 retracted 墓碑标记。"""
    __tablename__ = 'event_journal'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey('ingest_batches.id'), nullable=True)
    event_id: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int]
    op: Mapped[str] = mapped_column(String(12), default='upsert')  # upsert / retract
    retracted: Mapped[bool] = mapped_column(default=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Double)
