from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata
from src.utils.serialization import checksum
import math, time
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    for index,row in enumerate(data.records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='': raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), created_at=time.time())
    # 基线批次：自身即为链路根，有效快照等于原始记录
    d.root_id=d.id; d.parent_id=d.id
    d.effective_records=[dict(r) for r in data.records]
    d.effective_checksum=d.checksum
    db.add(d); db.flush()
    # flush 后 d.id 已生成，确保 root_id 指向自身
    d.root_id=d.id; d.parent_id=d.id
    return d
