import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum,
            'created_at':d.created_at, 'root_id':d.root_id, 'parent_id':d.parent_id,
            'effective_rows':len(d.effective_records) if d.effective_records is not None else len(d.records),
            'effective_checksum':d.effective_checksum, 'last_ingest_stats':d.last_ingest_stats,
            'kind':'derived' if d.parent_id and d.parent_id != d.id else 'baseline'}
def ingest_batch_dict(b):
    return {'id':b.id, 'dataset_id':b.dataset_id, 'derived_dataset_id':b.derived_dataset_id,
            'source':b.source, 'base_checksum':b.base_checksum,
            'checksum':b.checksum, 'stats':b.stats, 'created_at':b.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
