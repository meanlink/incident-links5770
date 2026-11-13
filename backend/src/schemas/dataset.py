from pydantic import BaseModel, Field
class DatasetInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source: str = Field(default='manual.json', max_length=200)
    records: list[dict] = Field(min_length=5, max_length=5000)
class IngestInput(BaseModel):
    # 增量事件：每条至少含 event_id、version（整数，>=1），op 默认 upsert；
    # retract 仅需 event_id+version+op，upsert 需携带完整业务字段。
    source: str = Field(default='supplement.json', max_length=200)
    records: list[dict] = Field(min_length=1, max_length=5000)
