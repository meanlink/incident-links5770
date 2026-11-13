import {api} from './client.js';
export const datasets={
 list:()=>api('/datasets'),
 get:id=>api('/datasets/'+id),
 create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)}),
 ingest:(id,data)=>api('/datasets/'+id+'/ingest',{method:'POST',body:JSON.stringify(data)}),
 batches:id=>api('/datasets/'+id+'/ingest-batches'),
 journal:id=>api('/datasets/'+id+'/journal'),
 lineage:id=>api('/datasets/'+id+'/lineage'),
};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
