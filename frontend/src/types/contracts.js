/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string,root_id:?number,parent_id:?number,effective_rows:number,effective_checksum:?string,last_ingest_stats:?IngestStats,kind:'baseline'|'derived'}} Dataset */
/** @typedef {{added:number,corrected:number,retracted:number,ignored:number,total:number,conflicts:number}} IngestStats */
/** @typedef {{id:number,dataset_id:number,source:string,base_checksum:string,checksum:string,stats:IngestStats,created_at:number}} IngestBatch */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
export {};
