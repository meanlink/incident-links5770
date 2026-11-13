from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset, IngestBatch, EventJournal
from src.schemas.dataset import DatasetInput, IngestInput
from src.middlewares.auth import current_user, can_write
from src.services import datasets
from src.services import ingestion
from src.services.audit import record
from src.utils.serialization import dataset_dict, ingest_batch_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
@router.post('',status_code=201)
def create(data:DatasetInput,db=Depends(get_db),u=Depends(can_write)):
    d=datasets.create(db,data); record(db,u.email,'dataset.create',{'id':d.id,'rows':len(d.records)})
    db.commit(); return dataset_dict(d)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return {**dataset_dict(d),'records':d.records}
@router.post('/{id}/ingest',status_code=201)
def incremental(id:int,data:IngestInput,db=Depends(get_db),u=Depends(can_write)):
    base=db.get(Dataset,id)
    if not base:raise HTTPException(404,'数据批次不存在')
    new_dataset,batch,stats=ingestion.ingest(db,base,data,u)
    record(db,u.email,'dataset.ingest',{'base':base.id,'derived':new_dataset.id,'batch':batch.id,
                                        'source':data.source,'stats':stats})
    db.commit()
    return {'dataset':dataset_dict(new_dataset),'batch':ingest_batch_dict(batch),'stats':stats}
@router.get('/{id}/ingest-batches')
def ingest_batches(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    root_id=d.root_id or d.id
    rows=db.scalars(select(IngestBatch).where(IngestBatch.dataset_id==root_id).order_by(IngestBatch.id.desc()))
    return [ingest_batch_dict(b) for b in rows]
@router.get('/{id}/journal')
def journal(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    root_id=d.root_id or d.id
    rows=db.scalars(select(EventJournal).where(EventJournal.dataset_id==root_id).order_by(
        EventJournal.event_id,EventJournal.version))
    return [{'event_id':j.event_id,'version':j.version,'op':j.op,'retracted':j.retracted,
             'payload':j.payload,'batch_id':j.batch_id,'checksum':j.checksum} for j in rows]
@router.get('/{id}/lineage')
def lineage(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    root_id=d.root_id or d.id
    chain=db.scalars(select(Dataset).where(
        (Dataset.root_id==root_id)|(Dataset.id==root_id)).order_by(Dataset.id))
    return [dataset_dict(x) for x in chain]
