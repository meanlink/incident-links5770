"""基于已有批次的增量接入：按事件版本合并更正与撤销。

规则（与业务口径一致）：
- 每个事件以 event_id 标识，携带单调递增的 version；归档补发的旧版事件允许晚到。
- 同版本内容完全相同视为重复补发（忽略，不改变有效事件）；乱序记录按版本归并不影响最终结果。
- 同版本但内容不同属于冲突：列出全部冲突并整批拒绝，任何记录都不接入。
- 撤销（retract）写入墓碑，最高版本为撤销的事件从有效事件中移除；撤销后再到的旧版不能复活。
- 旧批次及其分析结果永不回写；每次接入产生新的派生批次与不可变的接入台账。
"""
import copy
import math
import time

from fastapi import HTTPException
from sqlalchemy import select

from src.models import Dataset, IngestBatch, EventJournal
from src.services.business import metadata
from src.utils.serialization import checksum

# 事件载荷中用于比较“同一版本内容是否相同”的业务字段（不含版本/操作等控制字段）
PAYLOAD_KEYS = [c['key'] for c in metadata()['columns']]
REQUIRED_CONTROL = ('event_id', 'version')
VALID_OPS = ('upsert', 'retract')


def _validate_payload(row, index):
    """校验一条事件的业务字段，返回规整后的载荷（数值字段转 float）。"""
    if not isinstance(row, dict):
        raise HTTPException(422, f'第 {index + 1} 行必须是事件对象')
    event_id = row.get('event_id')
    if event_id is None or str(event_id).strip() == '':
        raise HTTPException(422, f'第 {index + 1} 行缺少复核事件ID')
    payload = {'event_id': str(event_id).strip()}
    for column in metadata()['columns']:
        key = column['key']
        if key == 'event_id':
            continue
        value = row.get(key)
        if value is None or value == '':
            raise HTTPException(422, f'第 {index + 1} 行缺少字段 {column["label"]}')
        if column['type'] == 'number':
            try:
                if isinstance(value, bool) or not math.isfinite(float(value)):
                    raise ValueError()
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                raise HTTPException(422, f'第 {index + 1} 行 {column["label"]} 必须为有限数值')
        payload[key] = value
    if not str(payload.get('service', '')).strip():
        raise HTTPException(422, f'第 {index + 1} 行服务名称不能为空')
    minute = payload.get('occurred_min')
    if minute is not None and minute < 0:
        raise HTTPException(422, f'第 {index + 1} 行周内累计分钟不能为负数')
    # 等级只有 1~3 三档，统一规整为 int，避免 3 与 3.0 被误判为内容不同
    severity = payload.get('severity')
    if severity is not None:
        if float(severity) not in (1.0, 2.0, 3.0):
            raise HTTPException(422, f'第 {index + 1} 行事件等级须为 1~3')
        payload['severity'] = int(float(severity))
    return payload


def _parse_control(row, index):
    for field in REQUIRED_CONTROL:
        if row.get(field) is None or row.get(field) == '':
            raise HTTPException(422, f'第 {index + 1} 行缺少控制字段 {field}')
    try:
        raw_version = row['version']
        if isinstance(raw_version, bool):
            raise ValueError()
        version = int(raw_version)
        if float(raw_version) != version:
            raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(422, f'第 {index + 1} 行版本号必须为整数')
    if version < 1:
        raise HTTPException(422, f'第 {index + 1} 行版本号须从 1 开始')
    op = str(row.get('op', 'upsert')).strip().lower()
    if op not in VALID_OPS:
        raise HTTPException(422, f'第 {index + 1} 行操作类型只支持 upsert 或 retract')
    return str(row['event_id']).strip(), version, op


def _payload_digest(payload):
    return checksum({k: payload.get(k) for k in PAYLOAD_KEYS})


def _journal_map(db, dataset_id):
    """读取该批次链上已有的全部事件版本，key=(event_id, version)。"""
    rows = db.scalars(select(EventJournal).where(EventJournal.dataset_id == dataset_id))
    return {(j.event_id, j.version): j for j in rows}


def _build_effective(journal):
    """从版本台账折叠出当前有效事件：每个 event_id 取最高版本，撤销墓碑剔除。

    乱序与重复不影响结果；已撤销事件的旧版本不会复活。
    """
    latest = {}
    for (event_id, version), entry in journal.items():
        current = latest.get(event_id)
        if current is None or version > current[0]:
            latest[event_id] = (version, entry)
    effective = []
    for event_id in sorted(latest):
        _, entry = latest[event_id]
        if entry.retracted or entry.op == 'retract':
            continue
        effective.append(copy.deepcopy(entry.payload))
    effective.sort(key=lambda r: (r['occurred_min'], r['event_id']))
    return effective


def _ensure_journal(db, root):
    """链路根首次增量接入时，把原始记录回填为 version=1 的台账（不动 records）。"""
    exists = db.scalar(select(EventJournal.id).where(EventJournal.dataset_id == root.id).limit(1))
    if exists:
        return
    now = time.time()
    for row in root.records:
        payload = {k: row.get(k) for k in PAYLOAD_KEYS}
        # 与增量校验保持同一规整口径（等级落 int），避免补发同内容时误判冲突
        payload['severity'] = int(float(payload['severity']))
        db.add(EventJournal(
            dataset_id=root.id, batch_id=None, event_id=payload['event_id'],
            version=1, op='upsert', retracted=False, payload=payload,
            checksum=_payload_digest(payload), created_at=now,
        ))
    db.flush()


def _ensure_lineage(db, dataset):
    if dataset.root_id is None:
        dataset.root_id = dataset.id
        dataset.parent_id = dataset.id
        dataset.effective_records = copy.deepcopy(dataset.records)
        dataset.effective_checksum = dataset.checksum
        db.flush()


def chain_root(db, dataset):
    """返回批次链的根数据集；派生批次与根共享同一份版本台账。"""
    _ensure_lineage(db, dataset)
    root = db.get(Dataset, dataset.root_id)
    if root is None:
        root = dataset
        dataset.root_id = dataset.id
        db.flush()
    return root


def ingest(db, base, data, user):
    """在 base 批次之上合并一个增量批次，返回 (新派生批次, 接入批次, 统计)。

    版本台账与接入台账统一归属链路根，多级增量仍能完整保留版本历史与撤销墓碑；
    发现同版本内容冲突时抛 409，整批不接入、不产生任何写入。
    """
    if not data.records:
        raise HTTPException(422, '增量批次至少包含一条事件')
    if len(data.records) > 5000:
        raise HTTPException(422, '单个增量批次不能超过 5000 条事件')

    _ensure_lineage(db, base)
    root = chain_root(db, base)
    _ensure_journal(db, root)
    journal = _journal_map(db, root.id)
    now = time.time()

    # 第一遍：校验并规整输入；同批内同 event_id+version 也参与冲突判定
    parsed = []
    incoming = {}
    for index, row in enumerate(data.records):
        event_id, version, op = _parse_control(row, index)
        payload = None
        if op == 'upsert':
            payload = _validate_payload(row, index)
            if payload['event_id'] != event_id:
                raise HTTPException(422, f'第 {index + 1} 行事件ID不一致')
        parsed.append({'event_id': event_id, 'version': version, 'op': op,
                       'payload': payload, 'index': index})
        key = (event_id, version)
        digest = _payload_digest(payload) if payload else 'retract'
        if key in incoming and incoming[key] != digest:
            raise HTTPException(409, {'message': '增量批次内部存在同一版本内容不同的事件，整批未接入',
                                      'conflicts': [{'event_id': event_id, 'version': version,
                                                     'reason': '同一批次内同一版本出现不同内容'}]})
        incoming.setdefault(key, digest)

    # 第二遍：与已有台账做同版本比对，收集全部冲突后整批拒绝
    conflicts = []
    for item in parsed:
        key = (item['event_id'], item['version'])
        existing = journal.get(key)
        if existing is None:
            continue
        if item['op'] == 'retract':
            if existing.op != 'retract' and not existing.retracted:
                conflicts.append({
                    'event_id': item['event_id'], 'version': item['version'],
                    'reason': '该版本已是有效事件，撤销须使用更高版本，不能改写同版本',
                    'incoming_op': 'retract', 'existing_op': existing.op,
                })
            continue
        incoming_digest = _payload_digest(item['payload'])
        if existing.op == 'retract' or existing.retracted:
            conflicts.append({
                'event_id': item['event_id'], 'version': item['version'],
                'reason': '该版本已撤销，同版本事件不能使其复活，请使用更高版本',
                'incoming_op': 'upsert', 'existing_op': 'retract',
            })
        elif existing.checksum != incoming_digest:
            conflicts.append({
                'event_id': item['event_id'], 'version': item['version'],
                'reason': '同一版本事件内容不同',
                'incoming': item['payload'], 'existing': existing.payload,
            })
    if conflicts:
        raise HTTPException(409, {'message': '发现同版本内容冲突的事件，整批未接入',
                                  'conflicts': conflicts})

    # 先落接入批次台账（IngestBatch 自身不可变），journal 新行直接挂 batch_id
    batch = IngestBatch(
        dataset_id=root.id, source=data.source,
        base_checksum=base.effective_checksum or base.checksum,
        checksum=checksum([{'event_id': i['event_id'], 'version': i['version'], 'op': i['op']}
                           for i in parsed]),
        stats={}, created_at=now,
    )
    db.add(batch)
    db.flush()

    # 第三遍：确认无冲突才写版本台账，逐条分类计数
    stats = {'added': 0, 'corrected': 0, 'retracted': 0, 'ignored': 0,
             'total': len(parsed), 'conflicts': 0}
    seen_keys = set()
    for item in parsed:
        key = (item['event_id'], item['version'])
        if key in journal or key in seen_keys:
            # 同版本同内容（含重复撤销、批内重复、乱序重放）：不改变有效事件
            stats['ignored'] += 1
            continue
        seen_keys.add(key)

        if item['op'] == 'retract':
            # 仅当该事件当前最高版本是有效 upsert 时，撤销才真正改变有效事件；
            # 最高版本已是墓碑（重复撤销）或事件从不存在时计入忽略。
            highest = max(
                (ver for (eid, ver) in journal if eid == item['event_id']),
                default=None,
            )
            had_live = highest is not None and not (
                journal[(item['event_id'], highest)].retracted
                or journal[(item['event_id'], highest)].op == 'retract'
            )
            entry = EventJournal(
                dataset_id=root.id, batch_id=batch.id, event_id=item['event_id'],
                version=item['version'], op='retract', retracted=True,
                payload={}, checksum='retract', created_at=now,
            )
            db.add(entry)
            journal[key] = entry
            if had_live:
                stats['retracted'] += 1
            else:
                # 撤销本就不存在或已撤销的事件，有效事件不变，计入忽略
                stats['ignored'] += 1
            continue

        has_prior = any(j.event_id == item['event_id'] for j in journal.values())
        entry = EventJournal(
            dataset_id=root.id, batch_id=batch.id, event_id=item['event_id'],
            version=item['version'], op='upsert', retracted=False,
            payload=item['payload'], checksum=_payload_digest(item['payload']),
            created_at=now,
        )
        db.add(entry)
        journal[key] = entry
        if has_prior:
            stats['corrected'] += 1
        else:
            stats['added'] += 1

    batch.stats = stats
    effective = _build_effective(journal)
    effective_checksum = checksum(effective)

    # 旧批次保持原样：合并结果落到一个新的派生批次
    stem = f'{base.name} · 增量{time.strftime("%m%d%H%M")}'
    name, serial = stem, 2
    while db.scalar(select(Dataset).where(Dataset.name == name)):
        name = f'{stem}-{serial}'
        serial += 1

    new_dataset = Dataset(
        name=name, source=data.source, records=effective,
        checksum=effective_checksum, created_at=now,
        root_id=root.id, parent_id=base.id,
        effective_records=effective, effective_checksum=effective_checksum,
        last_ingest_stats=stats,
    )
    db.add(new_dataset)
    db.flush()
    batch.derived_dataset_id = new_dataset.id
    db.flush()
    return new_dataset, batch, stats
