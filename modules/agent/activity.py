"""Local observation clocks; never infer server execution or private reasoning."""
import time
import math
import re
from uuid import uuid4

MAX_ELAPSED_MS = 31536000000

KINDS = frozenset({'reasoning', 'function_call', 'function_call_output', 'mcp_call',
    'command_execution', 'web_search_call', 'computer_use_call', 'computer_use_approval_request',
    'computer_use_approval_request_result', 'create_subagent_call', 'send_subagent_input_call',
    'resume_subagent_call', 'wait_for_subagents_call', 'interrupt_subagent_call',
    'close_subagent_call', 'agent_message'})


class ActivityClock:
    def __init__(self):
        self.records = {}
        self.clock_id = uuid4().hex
        self.origin = time.monotonic()

    def observe(self, item, *, first=False, phase=None):
        key, turn = item.get('id'), item.get('turn_id')
        if not isinstance(key, str) or not isinstance(turn, str) or item.get('type') not in KINDS:
            return
        record = self.records.get((turn, key))
        if record is None:
            record = dict(item_id=key, turn_id=turn, start=time.monotonic() if first else None, end=None,
                          phase='running')
            self.records[(turn, key)] = record
        if record['end'] is not None: return
        if phase=='running' and item['type']=='function_call' and record['start'] is None:
            record['start']=time.monotonic()
        status = item.get('status')
        if phase is None:
            phase = ('failed' if item.get('error') else 'waiting' if item['type']=='function_call' and status=='completed' else
                     'completed' if item['type']=='function_call_output' else
                     'waiting' if item['type']=='computer_use_approval_request' else
                     status if status in ('completed','failed','incomplete','cancelled') else 'running')
        record['phase'] = phase
        if phase in ('completed','failed','incomplete','cancelled'):
            record['end'] = time.monotonic()

    def finish_turn(self, turn, outcome):
        for (source_turn, _), record in self.records.items():
            if source_turn == turn and record['end'] is None:
                record['end'] = time.monotonic()
                record['phase'] = {'cancelled':'turn_cancelled','failed':'turn_failed'}.get(outcome,'incomplete')

    def snapshot(self):
        now = time.monotonic()
        return [dict(item_id=record['item_id'], turn_id=record['turn_id'], phase=record['phase'],
                     elapsed_ms=None if record['start'] is None else max(0, round(((now if record['end'] is None else record['end'])-record['start'])*1000)),
                     running=record['end'] is None, sampled_at=now,
                     **({'interval': dict(clock_id=self.clock_id, started_ms=(record['start']-self.origin)*1000,
                         ended_ms=None if record['end'] is None else (record['end']-self.origin)*1000,
                         sampled_ms=(now-self.origin)*1000)} if record['start'] is not None else {}))
                for record in self.records.values()]


def safe_interval(value):
    """Relative coordinates can only be compared within their observation clock."""
    if not isinstance(value, dict) or not isinstance(value.get('clock_id'), str) or not re.fullmatch(r'[a-f0-9]{32}', value['clock_id']):
        return None
    start, end, sample = (value.get(key) for key in ('started_ms', 'ended_ms', 'sampled_ms'))
    if any(type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= MAX_ELAPSED_MS for number in (start, sample)):
        return None
    if start > sample or end is not None and (type(end) not in (int, float) or not math.isfinite(end) or not start <= end <= sample):
        return None
    return dict(clock_id=value['clock_id'], started_ms=start, ended_ms=end, sampled_ms=sample)


def visible_activity_boundary(entry, *, active=False, clock=None):
    """Only invisible assistant/reasoning occurrences may bridge a tool run.

    Canonical entries stay in the timeline. Missing identity, files, capture
    notices and unknown kinds are not evidence that visible content is absent.
    """
    if entry.get('capture', {}).get('omitted') or entry.get('capture', {}).get('truncated'):
        return True
    if entry.get('files') or entry.get('file_refs'):
        return True
    if entry['kind'] == 'message' and entry.get('role') == 'assistant':
        return any(part.get('type') != 'text' or part.get('text', '').strip()
                   for part in entry.get('content', []))
    if entry['kind'] == 'summary':
        phase = ((clock or {}).get(entry.get('source_id'), {}).get('phase')
                 or entry.get('activity_phase') or entry.get('status'))
        return (any(part.get('type') != 'summary_text' or part.get('text', '').strip()
                    for part in entry.get('content', []))
                or active and phase in ('running', 'waiting', 'in_progress', 'requires_action'))
    return True


def contiguous_tool_runs(timeline, *, is_boundary=visible_activity_boundary):
    """Share visible display boundaries with durable group duration calculation."""
    result, boundaries, groups = [], {}, {}
    current = None
    for entry in timeline:
        turn = entry.get('turn_ref')
        if entry['kind'] != 'tool':
            if is_boundary(entry):
                current = None
                boundaries[turn] = (entry['id'], entry.get('identity') in ('api_id', 'application_occurrence'))
            elif current is not None and current['turn_ref'] != turn:
                current = None
            result.append(entry)
            continue
        if current is None or not turn or current['turn_ref'] != turn:
            boundary, stable = boundaries.get(turn, ('turn-start', True))
            current = dict(kind='tool_group', turn_ref=turn, entries=[], boundary=boundary, boundary_stable=stable, persist_open=stable)
            result.append(current)
            groups.setdefault((turn, boundary), []).append(current)
        current['entries'].append(entry)
        current['persist_open'] &= entry.get('identity') in ('api_id', 'application_occurrence')
    for repeats in groups.values():
        if len(repeats) > 1:
            for group in repeats: group['persist_open'] = False
    return result


def group_span(group, *, clock=None, active=False):
    """Earliest observed start to latest end; never sum overlapping tools."""
    entries = group['entries']
    if not entries or not group.get('persist_open') or not group.get('turn_ref'):
        return None
    intervals = []
    for entry in entries:
        if entry.get('identity') not in ('api_id', 'application_occurrence'):
            return None
        observed = (clock or {}).get(entry.get('source_id'), {})
        interval = safe_interval(observed.get('interval')) or safe_interval(entry.get('activity_interval'))
        if interval is None:
            return None
        if interval['ended_ms'] is None and not (active and safe_interval(observed.get('interval')) == interval and observed.get('running') is True):
            return None  # A saved live clock cannot restart in another worker/view.
        intervals.append(interval)
    if len({interval['clock_id'] for interval in intervals}) != 1:
        return None
    end = max(interval['sampled_ms'] if interval['ended_ms'] is None else interval['ended_ms'] for interval in intervals)
    elapsed = end - min(interval['started_ms'] for interval in intervals)
    if not 0 <= elapsed <= MAX_ELAPSED_MS:
        return None
    return dict(elapsed_ms=elapsed, running=any(interval['ended_ms'] is None for interval in intervals))


def persist_group_durations(timeline):
    """Recompute receipts after ordering, grouping and membership changes."""
    for entry in timeline: entry.pop('tool_group_duration', None)
    for group in contiguous_tool_runs(timeline):
        if group['kind'] != 'tool_group': continue
        span = group_span(group)
        if span:
            group['entries'][0]['tool_group_duration'] = dict(
                members=[entry['id'] for entry in group['entries']], elapsed_ms=span['elapsed_ms'])


def safe_records(values):
    if not isinstance(values,list):return []
    records=[]
    for value in values[:20000]:
        if not isinstance(value,dict):continue
        if any(not isinstance(value.get(key),str) or not value[key] or len(value[key])>512 for key in ('item_id','turn_id')):continue
        phase=value.get('phase')
        if phase not in ('running','waiting','completed','failed','incomplete','cancelled','turn_cancelled','turn_failed'):continue
        elapsed=value.get('elapsed_ms');sampled=value.get('sampled_at')
        if not (type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<=31536000000):elapsed=None
        if not (type(sampled) in (int,float) and math.isfinite(sampled) and 0<=sampled<=time.monotonic()+1):sampled=None
        interval = safe_interval(value.get('interval'))
        records.append(dict(item_id=value['item_id'],turn_id=value['turn_id'],phase=phase,elapsed_ms=elapsed,
                            sampled_at=sampled,running=value.get('running') is True and phase in ('running','waiting'),
                            **({'interval': interval} if interval else {})))
    return records
