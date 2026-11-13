import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify,date} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';

const canWrite=()=>session.user.role!=='viewer';
const statMeta=[['added','新增','oklch(48% 0.13 145)'],['corrected','更正','oklch(55% 0.12 220)'],['retracted','撤销','oklch(47% 0.15 30)'],['ignored','忽略','oklch(55% 0.03 80)']];

function statChips(stats){
 if(!stats)return '';
 return '<div class="stat-chips">'+statMeta.map(([k,label,color])=>'<span class="chip" style="--chip:'+color+'"><small>'+label+'</small><strong>'+esc(stats[k]??0)+'</strong></span>').join('')+'</div>';
}

function batchKindTag(d){
 return d.kind==='derived'?'<em class="kind-tag derived">增量派生</em>':'<em class="kind-tag base">基线批次</em>';
}

export async function dataPage(){
 workspace.datasets=await datasets.list();
 const first=workspace.datasets[0];
 let selected=first?await datasets.get(first.id):null;
 let batches=first?await datasets.batches(first.id):[];
 let lineage=first?await datasets.lineage(first.id):[];
 const m=workspace.meta;
 return heading('02 / DATA INTAKE','数据接入与批次追溯','保留原始业务字段、来源和内容指纹。归档补发的更正与撤销按事件版本增量合并；旧批次及其分析结果永不回写。')
 +'<div class="dataset-grid"><section class="panel">'
 +'<div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批 · 点击选择基线</span></div>'
 +'<div class="batch-list">'+workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong> '+batchKindTag(d)
   +'<span>'+d.rows+' 条有效事件 · '+esc(d.source)+'</span>'
   +(d.last_ingest_stats?'<span class="last-stats">最近增量：新增 '+d.last_ingest_stats.added+' / 更正 '+d.last_ingest_stats.corrected+' / 撤销 '+d.last_ingest_stats.retracted+' / 忽略 '+d.last_ingest_stats.ignored+'</span>':'')
   +'<small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small></button>').join('')+'</div>'
 +'<div class="section-title"><h2>接入新基线批次</h2></div>'
 +'<form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label>'
 +'<label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label>'
 +'<label>记录 JSON<textarea name="records" rows="5" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label>'
 +'<p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录。</p>'
 +'<button type="submit" class="primary" '+(canWrite()?'':'disabled')+'>校验并接入批次</button></form>'
 +'</section>'
 +'<section class="panel">'
 +'<div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无批次')+'</h2><span>有效事件预览前 30 条</span></div>'
 +(selected?'<div class="lineage-bar">'+lineage.map((d,i)=>(i?'<span class="lineage-arrow">→</span>':'')+'<button class="lineage-node" data-dataset="'+d.id+'">'+esc(d.name)+'</button>').join('')+'</div>':'')
 +'<div id="data-preview">'+table(m.columns,selected?.records.slice(0,30)||[])+'</div>'
 +(selected?'<div class="ingest-block"><div class="section-title"><h2>基于该批次增量接入</h2><span>更正/撤销/补发</span></div>'
   +'<form id="ingest-form">'
   +'<label>补发来源<input name="source" required placeholder="例如：archive-correction-w46.json"></label>'
   +'<label>上传增量 CSV 或 JSON<input type="file" id="ingest-file" accept=".json,.csv"></label>'
   +'<label>增量事件 JSON / CSV<textarea name="records" rows="7" placeholder="每条需含 event_id 与 version；撤销用 {&quot;event_id&quot;:&quot;QS-0001&quot;,&quot;version&quot;:2,&quot;op&quot;:&quot;retract&quot;}，更正携带完整业务字段并提升 version" required></textarea></label>'
   +'<p class="hint">同版本内容相同视为重复补发（忽略）；同版本内容不同会列出冲突并整批拒绝；撤销后旧版事件不能复活。乱序与重复不改变最终有效事件。</p>'
   +'<button type="submit" class="primary" '+(canWrite()?'':'disabled')+'>按版本合并并生成派生批次</button></form></div>':'')
 +'<div class="ingest-block"><div class="section-title"><h2>该批次链的接入台账</h2><span>新增/更正/撤销/忽略与来源</span></div>'
 +'<div id="ingest-batches">'+(batches.length?'<div class="batch-ledger">'+batches.map(b=>'<article class="ledger-item"><div><strong>#'+b.id+' · '+esc(b.source)+'</strong><span>'+date(b.created_at)+' · 指纹 '+esc(b.checksum.slice(0,12))+'…</span>'+statChips(b.stats)+'</div></article>').join('')+'</div>':'<p class="hint">该批次尚无增量接入；基线批次首次增量时会自动把原始事件登记为 version 1。</p>')+'</div></div>'
 +'</section></div>';
}

export function bindData(refresh){
 let source='manual.json';
 document.querySelector('#file-input')?.addEventListener('change',async e=>{
  try{const file=e.target.files[0];if(!file)return;source=file.name;
   const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);
   document.querySelector('#dataset-form [name=records]').value=JSON.stringify(records,null,2);
  }catch(error){notify(error.message,true);}
 });
 document.querySelector('#ingest-file')?.addEventListener('change',async e=>{
  try{const file=e.target.files[0];if(!file)return;
   const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);
   document.querySelector('#ingest-form [name=records]').value=JSON.stringify(records,null,2);
   const src=document.querySelector('#ingest-form [name=source]');
   if(src&&!src.value.trim())src.value=file.name;
  }catch(error){notify(error.message,true);}
 });
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{
  try{
   const d=await datasets.get(button.dataset.dataset);
   const [bs,lg]=await Promise.all([datasets.batches(d.id),datasets.lineage(d.id)]);
   document.querySelector('#preview-name').textContent=d.name;
   document.querySelector('#data-preview').innerHTML=table(workspace.meta.columns,d.records.slice(0,30));
   const bar=document.querySelector('.lineage-bar');
   if(bar)bar.innerHTML=lg.map((x,i)=>(i?'<span class="lineage-arrow">→</span>':'')+'<button class="lineage-node" data-dataset="'+x.id+'">'+esc(x.name)+'</button>').join('');
   document.querySelector('#ingest-batches').innerHTML=bs.length?'<div class="batch-ledger">'+bs.map(b=>'<article class="ledger-item"><div><strong>#'+b.id+' · '+esc(b.source)+'</strong><span>'+date(b.created_at)+' · 指纹 '+esc(b.checksum.slice(0,12))+'…</span>'+statChips(b.stats)+'</div></article>').join('')+'</div>':'<p class="hint">该批次尚无增量接入；基线批次首次增量时会自动把原始事件登记为 version 1。</p>';
   document.querySelector('#ingest-form')?.setAttribute('data-base',d.id);
   document.querySelectorAll('.lineage-node').forEach(n=>n.onclick=()=>{
    const target=document.querySelector('.batch-item[data-dataset="'+n.dataset.dataset+'"]');
    if(target)target.click();
   });
  }catch(error){notify(error.message,true);}
 });
 const firstForm=document.querySelector('#dataset-form');
 if(firstForm)submit(firstForm,async f=>{
  await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});
  notify('基线批次已接入');await refresh();
 });
 const ingestForm=document.querySelector('#ingest-form');
 if(ingestForm){
  const selectedId=workspace.datasets[0]?.id;
  ingestForm.setAttribute('data-base',selectedId);
  submit(ingestForm,async f=>{
   const baseId=Number(ingestForm.getAttribute('data-base'));
   const body={source:f.get('source')||'supplement.json',records:JSON.parse(f.get('records'))};
   try{
    const r=await datasets.ingest(baseId,body);
    notify('增量已合并：新增 '+r.stats.added+' · 更正 '+r.stats.corrected+' · 撤销 '+r.stats.retracted+' · 忽略 '+r.stats.ignored);
   }catch(error){
    // 409 冲突响应 detail 为 {message, conflicts:[...]}，提炼出可读摘要
    let message=error.message;
    try{
      const parsed=JSON.parse(error.message);
      if(parsed&&Array.isArray(parsed.conflicts)){
       const ids=[...new Set(parsed.conflicts.map(c=>c.event_id+'@v'+c.version))].slice(0,5).join('、');
       message=(parsed.message||'发现版本冲突')+'：'+ids+'（共 '+parsed.conflicts.length+' 条，整批未接入）';
      }
    }catch(_){/* 普通字符串错误保持原样 */}
    notify(message,true);
    return;
   }
   await refresh();
  });
 }
}
