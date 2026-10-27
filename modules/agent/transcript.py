"""Bounded, inert Agent history snapshots. No SDK, I/O, credentials or UI.

API IDs are provenance, never capabilities. Download availability is supplied
only by a caller-owned resolver. Persisted items, not stream deltas, are inputs.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from modules.agent.activity import safe_interval, persist_group_durations

VERSION = 1
FORMAT_VERSION = 2
SDK_VERSION = '3.22.0'
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 20000
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_TOOL_BYTES = 16 * 1024
MAX_TOOL_TOTAL_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 8
MAX_CHILDREN = 100
_SECRET = re.compile(r'(?i)(?:api[_-]?key|authorization|password|passwd|cookie|credential(?:_values)?|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret|token)')
_DENIED = {'reasoning', 'encrypted_content', 'encrypted', 'chain_of_thought'}
_TOOLS = {'function_call', 'function_call_output', 'mcp_call', 'command_execution',
          'web_search_call', 'computer_use_call', 'computer_use_approval_request',
          'computer_use_approval_request_result', 'create_subagent_call',
          'send_subagent_input_call', 'resume_subagent_call', 'wait_for_subagents_call',
          'interrupt_subagent_call', 'close_subagent_call', 'agent_message'}
_TOOL_FIELDS = {'function_call': ('call_id', 'name', 'arguments'),
                'function_call_output': ('call_id', 'output', 'error'),
                'mcp_call': ('server_label', 'name', 'arguments', 'output', 'error'),
                'command_execution': ('command', 'cwd', 'duration_ms', 'exit_code', 'output'),
                'web_search_call': ('action',), 'computer_use_call': ('title', 'screenshot_available_in_source'),
                'create_subagent_call': ('agent_id', 'model', 'reasoning_effort'),
                'agent_message': ('sender_agent_id', 'recipient_agent_id'),
                'send_subagent_input_call': ('sender_agent_id', 'recipient_agent_id'),
                'computer_use_approval_request': ('summary',),
                'computer_use_approval_request_result': ('summary',)}
_LEGACY_FIELDS = {'system', 'model_name', 'model_selection', 'single_turn', 'temperature',
                  'top_p', 'n_choices', 'stop_sequence', 'token_upper_limit',
                  'max_generation_token', 'presence_penalty', 'frequency_penalty',
                  'logit_bias', 'user_identifier', 'stream', 'metadata'}


class TranscriptError(ValueError):
    pass


class UnsupportedVersion(TranscriptError):
    """Do not overwrite a history that this reader cannot preserve."""


def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,512}', value) and not value.startswith('sk-') else None


def _id(scope, kind, source):
    wire = json.dumps([scope, kind, source], ensure_ascii=False, separators=(',', ':'))
    return kind + '-' + hashlib.sha256(wire.encode()).hexdigest()


def _source_id(value, secrets):
    identity = _identifier(value)
    if identity is None or any(secret and secret in identity for secret in secrets):
        return None
    return identity


def _bounded_text(value, limit, secrets=()):
    if not isinstance(value, str):
        return '', {'omitted': True}
    text = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)', '', value)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    for secret in secrets:
        if isinstance(secret, str) and secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\bBearer\s+[^\s,;"\']+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    # URLs are handled by safe_url; a query parameter must not consume the
    # remaining innocent parameters as an unquoted credential header.
    key = r'(?i)(?<![?&])(\b(?:api[_-]?key|authorization|password|passwd|cookie|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret|token)\b["\']?\s*[:=]\s*)'
    text = re.sub(key + r'"(?:\\.|[^"\\])*"', r'\1[REDACTED]', text)
    text = re.sub(key + r"'(?:\\.|[^'\\])*'", r'\1[REDACTED]', text)
    text = re.sub(key + r'[^\n]+', r'\1[REDACTED]', text)
    # URL secrets in otherwise ordinary command/output text are cleaned too.
    text = re.sub(r'https?://[^\s<>"\']+', lambda m: safe_url(m.group(), secrets=secrets) or '[URL OMITTED]', text)
    encoded = text.encode('utf-8', errors='replace')
    truncated = len(encoded) > limit
    if truncated:
        text = encoded[:limit].decode('utf-8', errors='ignore')
    return text, {'redacted': text != value and not truncated, 'truncated': truncated}


def safe_url(value, *, secrets=()):
    """Display-only HTTP(S) URL; never fetch it. Credentials are removed."""
    if not isinstance(value, str) or len(value) > 8192 or re.search(r'[\x00-\x20\x7f]', value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname:
            return None
        host = url.hostname
        if ':' in host:
            host = '[' + host + ']'
        if url.port:
            host += ':' + str(url.port)
        query = []
        for key, value in parse_qsl(url.query, keep_blank_values=True):
            original_key = key
            for secret in secrets:
                if secret:
                    key = key.replace(secret, '[REDACTED]')
            value = '[REDACTED]' if _SECRET.search(original_key) or any(s and s in value for s in secrets) else value
            query.append((key, value))
        path = url.path
        for secret in secrets:
            if secret:
                path = path.replace(secret, '[REDACTED]')
        return urlunsplit((url.scheme, host, path, urlencode(query), ''))
    except (ValueError, TypeError):
        return None


def sanitize(value, *, secrets=(), max_bytes=MAX_TOOL_BYTES):
    """Return (safe JSON value, capture flags); this is not lossless raw storage."""
    if type(max_bytes) is not int or max_bytes < 2:
        raise TranscriptError('A JSON byte budget must be an integer of at least two')
    flags = {'redacted': False, 'truncated': False, 'omitted': False}
    def visit(item, depth):
        if depth > MAX_DEPTH:
            flags['truncated'] = True
            return '[DEPTH LIMIT]'
        if isinstance(item, str):
            out, state = _bounded_text(item, max_bytes, secrets)
            for key in flags:
                flags[key] |= state.get(key, False)
            return out
        if item is None or type(item) in (bool, int):
            return item
        if type(item) is float and math.isfinite(item):
            return item
        if isinstance(item, (list, tuple)):
            flags['truncated'] |= len(item) > MAX_CHILDREN
            return [visit(x, depth + 1) for x in item[:MAX_CHILDREN]]
        if isinstance(item, dict):
            if isinstance(item.get('type'), str) and item['type'] in _DENIED:
                flags['omitted'] = True
                return '[OMITTED CONTENT]'
            out = {}
            flags['truncated'] |= len(item) > MAX_CHILDREN
            for key, entry in list(item.items())[:MAX_CHILDREN]:
                if not isinstance(key, str):
                    flags['omitted'] = True
                    continue
                if key.lower() in _DENIED:
                    flags['omitted'] = True
                    continue
                safe_key, state = _bounded_text(key, 128, secrets)
                # Clean keys as well as values. Distinct keys that clean or
                # truncate alike retain separate values via stable suffixes.
                base_key = safe_key
                suffix = 1
                while safe_key in out:
                    suffix += 1
                    marker = '#' + str(suffix)
                    safe_key = _bounded_text(base_key, 128 - len(marker))[0] + marker
                for flag in ('redacted', 'truncated', 'omitted'):
                    flags[flag] |= state.get(flag, False)
                flags['redacted'] |= base_key != key
                if _SECRET.search(key):
                    out[safe_key] = '[REDACTED]'
                    flags['redacted'] = True
                else:
                    out[safe_key] = visit(entry, depth + 1)
            return out
        flags['omitted'] = True
        return '[UNSUPPORTED VALUE]'
    result = visit(value, 0)
    def encoded_json(item):
        return json.dumps(item, ensure_ascii=False, allow_nan=False).encode()
    encoded = encoded_json(result)
    if len(encoded) > max_bytes:
        # The preview itself is JSON-escaped again. Budget that FINAL encoding,
        # not the original bytes; quotes/backslashes/Unicode must remain bounded.
        preview = encoded.decode('utf-8')
        if len(encoded_json({'preview': ''})) > max_bytes:
            result = ''
            flags['omitted'] = True
        else:
            low, high = 0, len(preview)
            while low < high:
                middle = (low + high + 1) // 2
                if len(encoded_json({'preview': preview[:middle]})) <= max_bytes:
                    low = middle
                else:
                    high = middle - 1
            result = {'preview': preview[:low]}
        flags['truncated'] = True
    return result, flags


def _text(value, *, secrets=()):
    if not isinstance(value, str) or len(value.encode('utf-8', errors='replace')) > MAX_TEXT_BYTES:
        raise TranscriptError('Message text is invalid or exceeds the history limit')
    return _bounded_text(value, MAX_TEXT_BYTES, secrets)[0]


def _records(values):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_RECORDS:
        raise TranscriptError('History record count is invalid or exceeds the limit')
    if any(not isinstance(x, dict) for x in values):
        raise TranscriptError('History records must be objects')
    return values


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _filename(value):
    name = (value if isinstance(value, str) else 'file').replace('\\', '/').rsplit('/', 1)[-1]
    return re.sub(r'[\x00-\x1f\x7f]', '', name)[:255] or 'file'


def _flags(previous, current):
    """Do not erase earlier capture loss when a safe snapshot is reloaded."""
    previous = previous if isinstance(previous, dict) else {}
    return {key: previous.get(key) is True or current.get(key) is True
            for key in ('redacted', 'truncated', 'omitted')}


def _tool_details(kind, item, secrets):
    """The same display allowlist applies to API snapshots and imported JSON."""
    details = {key: item[key] for key in _TOOL_FIELDS.get(kind, ()) if key in item}
    if kind == 'web_search_call':
        action = item.get('action')
        details['action'] = None
        if isinstance(action, dict) and action.get('type') in ('search', 'open_page', 'find_in_page', 'other'):
            action_kind = action['type']
            filtered = {'type': action_kind}
            for key in ('query', 'queries') if action_kind == 'search' else ('pattern',) if action_kind == 'find_in_page' else ():
                if key in action:
                    filtered[key] = action[key]
            if action_kind in ('open_page', 'find_in_page'):
                filtered['url'] = safe_url(action.get('url'), secrets=secrets)
            details['action'] = filtered
    if kind in ('computer_use_approval_request', 'computer_use_approval_request_result'):
        details = {'summary': 'browser authentication request' if kind.endswith('request') else 'browser authentication response'}
    if kind == 'computer_use_call':
        details['screenshot_available_in_source'] = item.get('screenshot_available_in_source') is True or bool(item.get('output'))
    return details


def _safe_details(details, secrets, limit):
    """Bound each field without replacing the tool's outer display shape."""
    if limit < 256:
        return {}, {'omitted': bool(details), 'truncated': bool(details), 'redacted': False}
    out, flags = {}, {'omitted': False, 'truncated': False, 'redacted': False}
    allowance = max(128, limit // max(len(details), 1) - 128)
    for key, value in details.items():
        safe, state = sanitize(value, secrets=secrets, max_bytes=allowance)
        out[key] = safe
        flags = _flags(flags, state)
    while out and len(json.dumps(out, ensure_ascii=False).encode()) > limit:
        out.pop(next(reversed(out)))
        flags.update(omitted=True, truncated=True)
    return out, flags


def _summary(parts, secrets, budget=MAX_TOOL_BYTES):
    limit=max(0,budget)
    content=[];flags={'omitted':False,'truncated':False,'redacted':False}
    parts=_records(parts)
    if len(parts)>MAX_CHILDREN:raise TranscriptError('Too many public summary parts')
    for part in parts:
        if part.get('type')=='summary_text' and isinstance(part.get('text'),str):
            remaining=max(0,budget-512)
            text,state=_bounded_text(part['text'],remaining,secrets)
            flags=_flags(flags,state)
            if remaining:
                content.append({'type':'summary_text','text':text})
                budget-=len(text.encode('utf-8'))+128
            else:flags.update(omitted=True,truncated=True)
        else:flags['omitted']=True
    while content and len(json.dumps(content,ensure_ascii=False).encode())>limit:
        content.pop();flags.update(omitted=True,truncated=True)
    return content,flags


def _activity_metadata(record, source):
    index=source.get('output_index')
    if source.get('role')!='user' and type(index) is int and 0<=index<MAX_RECORDS:record['output_index']=index
    elapsed=source.get('elapsed_ms')
    if type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<=31536000000:
        record['elapsed_ms']=round(elapsed)
    phase=source.get('activity_phase')
    if phase in ('running','waiting','completed','failed','incomplete','cancelled','turn_cancelled','turn_failed'):
        record['activity_phase']=phase
    interval = safe_interval(source.get('activity_interval'))
    if interval: record['activity_interval'] = interval


def _ordered_timeline(records):
    for turn in {record.get('turn_ref') for record in records}:
        if turn is None:continue
        slots=[i for i,record in enumerate(records) if record.get('turn_ref')==turn and 'output_index' in record]
        indices=[records[i]['output_index'] for i in slots]
        if len(indices)!=len(set(indices)):continue
        values=sorted((records[i] for i in slots),key=lambda record:record['output_index'])
        for i,record in zip(slots,values):records[i]=record
    return records


def normalize(items, *, scope_id, turns=(), artifacts=(), input_mappings=(),
              capture=None, secrets=(), session_id=None, occurrence_ids=None, activity=()):
    """Normalize a root-Agent snapshot. Optional session_id filters artifacts.

    input_mappings: explicit item_id/turn_id + files, optionally display text;
    legacy wire_sha256 mappings are accepted only when one user item matches.
    Artifact message_item_id is an application receipt, not an API claim.
    occurrence_ids maps input positions to stable application receipt IDs. Null
    API IDs without such receipts may be displayed but cannot incrementally
    replace a nonempty history: a partial list position is not message identity.
    """
    if not _source_id(scope_id, secrets):
        raise TranscriptError('A stable local conversation scope is required')
    if occurrence_ids is None:
        occurrence_ids = {}
    if (not isinstance(occurrence_ids, dict) or
            any(type(key) is not int or key < 0 or key >= len(items) or not _source_id(value, secrets)
                for key, value in occurrence_ids.items())):
        raise TranscriptError('Occurrence IDs must be stable receipt strings keyed by input position')
    result = {'version': VERSION, 'scope_id': scope_id, 'sdk_version': SDK_VERSION,
              'capture': {'items': 'partial', 'turns': 'partial' if turns else 'not_collected',
                          'artifacts': 'partial' if artifacts else 'not_collected',
                          'input_files': 'partial' if input_mappings else 'not_collected', 'subagents': 'not_collected'},
              'turns': [], 'timeline': [], 'files': []}
    for key, value in (capture or {}).items():
        if key in result['capture'] and value in ('complete', 'partial', 'not_collected'):
            result['capture'][key] = value
    # This module does not collect subagents; callers cannot claim otherwise.
    result['capture']['subagents'] = 'not_collected'
    turn_ids = {}
    def turn_ref(source):
        source = _source_id(source, secrets)
        if source is None:
            return None
        if source not in turn_ids:
            local = _id(scope_id, 'turn', source)
            turn_ids[source] = local
            result['turns'].append({'id': local, 'source_id': source, 'status': None, 'capture': 'reference_only'})
        return turn_ids[source]
    for turn in _records(turns):
        source = _source_id(turn.get('id'), secrets)
        if source is None:
            continue
        ref = turn_ref(source)
        record = next(x for x in result['turns'] if x['id'] == ref)
        record.update(status=_identifier(turn.get('status')), capture='persisted_turn')
        for key in ('created_at', 'started_at', 'completed_at'):
            record[key] = _number(turn.get(key))
        if _source_id(turn.get('agent_id'), secrets):
            record['agent_source_id'] = turn['agent_id']
        if _source_id(turn.get('subagent_id'), secrets):
            record['subagent_source_id'] = turn['subagent_id']
        if turn.get('error') is not None:
            record['error'], record['error_capture'] = sanitize(turn['error'], secrets=secrets)
        if isinstance(turn.get('usage'), dict):
            record['usage'] = {key: _number(turn['usage'].get(key)) for key in ('input_tokens', 'output_tokens', 'total_tokens')}
    # Preserve first occurrence ordering; final repeated copies replace stale ones.
    unique, source_kinds, identities = {}, {}, {}
    for position, item in enumerate(_records(items)):
        kind = item.get('type')
        if isinstance(kind, str) and kind in _DENIED and kind!='reasoning':
            continue
        if kind=='reasoning':
            summary=item.get('summary')
            if not isinstance(summary,list) or (summary and not any(isinstance(part,dict) and part.get('type')=='summary_text' and isinstance(part.get('text'),str) for part in summary)):
                continue
        source = _source_id(item.get('id'), secrets)
        if source:
            if source in source_kinds and source_kinds[source] != kind:
                raise TranscriptError('Conflicting item types for one source ID')
            source_kinds[source] = kind
        occurrence = occurrence_ids.get(position)
        key = ('occurrence', occurrence) if occurrence else source or ('unresolved', _source_id(item.get('turn_id'), secrets), position)
        previous = unique.get(key)
        if previous and previous.get('type') != kind:
            raise TranscriptError('Conflicting item types for one occurrence ID')
        if previous and previous.get('status') in ('completed', 'failed', 'incomplete') and item.get('status') == 'in_progress':
            continue
        unique[key] = item
        identities[key] = 'application_occurrence' if occurrence else 'api_id' if source else 'unresolved'
    observed={(record.get('turn_id'),record.get('item_id')):record for record in _records(activity)}
    source_entries, user_hashes = {}, {}
    tool_budget = MAX_TOOL_TOTAL_BYTES
    for position, (identity, item) in enumerate(unique.items()):
        kind = item.get('type')
        source = _source_id(item.get('id'), secrets)
        ref = turn_ref(item.get('turn_id'))
        base = {'id': _id(scope_id, 'entry', identity), 'source_id': source, 'identity': identities[identity], 'turn_ref': ref,
                'status': _identifier(item.get('status')), 'file_refs': []}
        _activity_metadata(base,item)
        clock=observed.get((item.get('turn_id'),source)) if source else None
        if clock:_activity_metadata(base,dict(elapsed_ms=clock.get('elapsed_ms'),activity_phase=clock.get('phase'),activity_interval=clock.get('interval')))
        if kind == 'message' and item.get('role') in ('user', 'assistant'):
            base.update(kind='message', role=item['role'], phase=item.get('phase') if item.get('phase') in ('commentary', 'final_answer') else None,
                        content=[], capture={'origin': 'persisted_item', 'omitted': False})
            parts = item.get('content') or []
            if not isinstance(parts, list) or len(parts) > MAX_CHILDREN:
                raise TranscriptError('Invalid message content')
            for part in parts:
                if not isinstance(part, dict):
                    base['capture']['omitted'] = True
                elif part.get('type') in ('input_text', 'output_text', 'text') and isinstance(part.get('text'), str):
                    text = _text(part['text'], secrets=secrets)
                    base['content'].append({'type': 'text', 'text': text})
                    base['capture']['redacted'] = base['capture'].get('redacted', False) or text != part['text']
                else:
                    # Remote image URLs/base64 are not a file capability or an
                    # automatic network request. Keep a visible missing-media part.
                    base['content'].append({'type': 'media_placeholder', 'media_kind': 'image' if part.get('type') == 'input_image' else 'unsupported'})
                    base['capture']['omitted'] = True
            if base['role'] == 'user':
                wire = '\n'.join(p.get('text', '') for p in parts if isinstance(p, dict) and p.get('type') in ('input_text', 'text') and isinstance(p.get('text'), str))
                user_hashes.setdefault(hashlib.sha256(wire.encode()).hexdigest(), []).append(base)
        elif kind=='reasoning':
            content,flags=_summary(item.get('summary',[]),secrets,min(MAX_TOOL_BYTES,tool_budget))
            tool_budget-=len(json.dumps(content,ensure_ascii=False).encode())
            flags['omitted'] |= bool(item.get('content') or item.get('encrypted_content'))
            base.update(kind='summary',source_type='reasoning',content=content,capture=dict(flags,origin='persisted_item'))
        elif isinstance(kind, str) and kind in _TOOLS:
            base.update(kind='tool', source_type=kind)
            details = _tool_details(kind, item, secrets)
            base['details'], flags = _safe_details(details, secrets, min(MAX_TOOL_BYTES, tool_budget))
            size = len(json.dumps(base['details'], ensure_ascii=False).encode())
            if size > tool_budget:
                base['details'] = {}
                flags.update(omitted=True, truncated=True)
            else:
                tool_budget -= size
            flags['omitted'] |= bool(item.get('output')) if kind == 'computer_use_call' else bool(item.get('content'))
            base['capture'] = dict(flags, origin='persisted_item')
        else:
            base.update(kind='unsupported', source_type=_identifier(kind), capture={'omitted': True})
        result['timeline'].append(base)
        if source:
            source_entries[source] = base
    file_ids = {}
    def add_file(record, kind, target=None):
        source = _source_id(record.get('id') or record.get('input_id'), secrets)
        source_turn = _source_id(record.get('turn_id'), secrets)
        identity = [kind, source, source_turn, target['id'] if target and kind == 'input' else None] if source else [kind, len(result['files'])]
        local = _id(scope_id, 'file', identity)
        if local not in file_ids:
            name = record.get('name') or record.get('path') or record.get('filename')
            file = {'id': local, 'source_id': source, 'kind': kind, 'turn_ref': turn_ref(source_turn),
                    'name': _text(_filename(name), secrets=secrets), 'size_bytes': _number(record.get('size_bytes', record.get('size'))),
                    'created_at': _number(record.get('created_at')),
                    'availability': 'metadata_only', 'attachment': {'basis': 'turn_only' if source_turn else 'unresolved', 'message_ref': None}}
            result['files'].append(file)
            file_ids[local] = file
        file = file_ids[local]
        if target is not None:
            existing = file['attachment']['message_ref']
            if existing is not None and existing != target['id']:
                raise TranscriptError('A file reference has conflicting message attachments')
            file['attachment'] = {'basis': 'application_mapping', 'message_ref': target['id']}
            if local not in target['file_refs']:
                target['file_refs'].append(local)
        return file
    for mapping in _records(input_mappings):
        target = source_entries.get(mapping.get('item_id'))
        if target is not None and target.get('role') != 'user':
            target = None
        if target is None and mapping.get('wire_sha256'):
            candidates = user_hashes.get(mapping['wire_sha256'], [])
            target = candidates[0] if len(candidates) == 1 else None
        if target is not None and isinstance(mapping.get('text'), str):
            target['content'] = [{'type': 'text', 'text': _text(mapping['text'], secrets=secrets)}]
        for record in _records(mapping.get('files') or []):
            data = dict(record, turn_id=mapping.get('turn_id') or (next((k for k, v in turn_ids.items() if target and v == target['turn_ref']), None)))
            add_file(data, 'input', target)
    for artifact in _records(artifacts):
        if session_id is not None and artifact.get('session_id') not in (None, session_id):
            continue
        target = source_entries.get(artifact.get('message_item_id'))
        if target is not None and (target.get('role') != 'assistant' or target['turn_ref'] != turn_ref(artifact.get('turn_id'))):
            target = None
        add_file(artifact, 'generated', target)
    persist_group_durations(result['timeline'])
    return result


def legacy_projection(transcript):
    """Compatibility text only. New readers must render the transcript itself."""
    history, rows = [], []
    for entry in transcript['timeline']:
        if entry.get('kind') != 'message':
            continue
        text = '\n'.join(x['text'] for x in entry.get('content', []) if x.get('type') == 'text')
        role = entry['role']
        history.append({'role': role, 'content': text})
        if role == 'user':
            rows.append([text, None])
        elif rows and rows[-1][1] is None:
            rows[-1][1] = text
        else:
            rows.append([None, text])
    return history, rows


def _validate(transcript, *, secrets=()):
    """Rebuild exported known fields; ignore untrusted capabilities/extensions."""
    if not isinstance(transcript, dict) or transcript.get('version') != VERSION:
        raise UnsupportedVersion('Unsupported Agent transcript version; preserve the source file')
    scope = transcript.get('scope_id')
    if not _source_id(scope, secrets):
        raise TranscriptError('Invalid transcript scope')
    out = {'version': VERSION, 'scope_id': scope, 'sdk_version': SDK_VERSION,
           'capture': {}, 'turns': [], 'timeline': [], 'files': []}
    capture = transcript.get('capture', {})
    if not isinstance(capture, dict):
        raise TranscriptError('Invalid capture metadata')
    for key in ('items', 'turns', 'artifacts', 'input_files', 'subagents'):
        value = capture.get(key)
        out['capture'][key] = value if value in ('complete', 'partial', 'not_collected') else 'partial'
    out['capture']['subagents'] = 'not_collected'
    ids, turn_ids, file_ids = set(), set(), set()
    def unique(record, collection):
        identity = _identifier(record.get('id'))
        if not identity or identity in collection:
            raise TranscriptError('Invalid or duplicate local record ID')
        collection.add(identity)
        return identity
    for turn in _records(transcript.get('turns', [])):
        record = {'id': unique(turn, turn_ids), 'source_id': _source_id(turn.get('source_id'), secrets),
                  'status': _identifier(turn.get('status')), 'capture': turn.get('capture') if turn.get('capture') in ('persisted_turn', 'reference_only') else 'imported_snapshot'}
        for key in ('created_at', 'started_at', 'completed_at'):
            record[key] = _number(turn.get(key))
        for key in ('agent_source_id', 'subagent_source_id'):
            if _source_id(turn.get(key), secrets):
                record[key] = turn[key]
        if turn.get('error') is not None:
            record['error'], flags = sanitize(turn['error'], secrets=secrets)
            record['error_capture'] = _flags(turn.get('error_capture'), flags)
        if isinstance(turn.get('usage'), dict):
            record['usage'] = {key: _number(turn['usage'].get(key)) for key in ('input_tokens', 'output_tokens', 'total_tokens')}
        out['turns'].append(record)
    budget = MAX_TOOL_TOTAL_BYTES
    for entry in _records(transcript.get('timeline', [])):
        identity = unique(entry, ids)
        ref = entry.get('turn_ref')
        if ref is not None and (not _identifier(ref) or ref not in turn_ids):
            raise TranscriptError('Dangling turn reference')
        mode = entry.get('identity')
        if mode not in ('application_occurrence', 'api_id', 'unresolved'):
            mode = 'api_id' if _source_id(entry.get('source_id'), secrets) else 'unresolved'
        record = {'id': identity, 'source_id': _source_id(entry.get('source_id'), secrets), 'identity': mode, 'turn_ref': ref,
                  'status': _identifier(entry.get('status')), 'file_refs': []}
        if entry.get('kind') == 'message' and entry.get('role') in ('user', 'assistant'):
            record.update(kind='message', role=entry['role'], phase=entry.get('phase') if entry.get('phase') in ('commentary', 'final_answer') else None, content=[])
            for part in _records(entry.get('content', [])):
                if part.get('type') == 'text':
                    record['content'].append({'type': 'text', 'text': _text(part.get('text'), secrets=secrets)})
                else:
                    record['content'].append({'type': 'media_placeholder', 'media_kind': 'image' if part.get('media_kind') == 'image' else 'unsupported'})
            flags = _flags(entry.get('capture'), {'omitted': any(x['type'] != 'text' for x in record['content'])})
            record['capture'] = dict(flags, origin='imported_snapshot')
        elif entry.get('kind')=='summary' and entry.get('source_type')=='reasoning':
            content,flags=_summary(entry.get('content',[]),secrets,min(MAX_TOOL_BYTES,budget))
            budget-=len(json.dumps(content,ensure_ascii=False).encode())
            record.update(kind='summary',source_type='reasoning',content=content,
                          capture=dict(_flags(entry.get('capture'),flags),origin='imported_snapshot'))
        elif entry.get('kind') == 'tool' and isinstance(entry.get('source_type'), str) and entry.get('source_type') in _TOOLS:
            original_details = entry.get('details') or {}
            if not isinstance(original_details, dict):
                raise TranscriptError('Invalid tool display details')
            display_details = _tool_details(entry['source_type'], original_details, secrets)
            details, flags = _safe_details(display_details, secrets, min(MAX_TOOL_BYTES, budget))
            flags['omitted'] |= bool(set(original_details) - set(display_details))
            size = len(json.dumps(details, ensure_ascii=False).encode())
            if size > budget:
                details, flags = {}, dict(flags, omitted=True, truncated=True)
            else:
                budget -= size
            record.update(kind='tool', source_type=entry['source_type'], details=details,
                          capture=dict(_flags(entry.get('capture'), flags), origin='imported_snapshot'))
        else:
            record.update(kind='unsupported', source_type=_identifier(entry.get('source_type')), capture={'omitted': True})
        refs = entry.get('file_refs', [])
        if not isinstance(refs, list) or any(not _identifier(x) for x in refs):
            raise TranscriptError('Invalid file references')
        record['file_refs'] = list(dict.fromkeys(refs))
        _activity_metadata(record,entry)
        out['timeline'].append(record)
    _ordered_timeline(out['timeline'])
    by_entry = {x['id']: x for x in out['timeline']}
    for file in _records(transcript.get('files', [])):
        identity = unique(file, file_ids)
        ref = file.get('turn_ref')
        if ref is not None and (not _identifier(ref) or ref not in turn_ids):
            raise TranscriptError('Dangling file turn reference')
        attachment = file.get('attachment') or {}
        if not isinstance(attachment, dict):
            raise TranscriptError('Invalid file attachment')
        message = attachment.get('message_ref')
        if message is not None and (not _identifier(message) or message not in by_entry or by_entry[message]['kind'] != 'message'):
            raise TranscriptError('Dangling file message reference')
        if message is not None and by_entry[message]['turn_ref'] != ref:
            raise TranscriptError('File/message turn mismatch')
        record = {'id': identity, 'source_id': _source_id(file.get('source_id'), secrets), 'kind': file.get('kind') if file.get('kind') in ('input', 'generated', 'legacy') else 'legacy',
                  'turn_ref': ref, 'name': _text(_filename(file.get('name')), secrets=secrets), 'size_bytes': _number(file.get('size_bytes')), 'created_at': _number(file.get('created_at')),
                  'availability': 'metadata_only', 'attachment': {'message_ref': message, 'basis': 'application_mapping' if message else 'turn_only' if ref else 'unresolved'}}
        out['files'].append(record)
        if message is not None and identity not in by_entry[message]['file_refs']:
            raise TranscriptError('File attachment is not referenced by its message')
    for entry in out['timeline']:
        for ref in entry['file_refs']:
            file = next((f for f in out['files'] if f['id'] == ref), None)
            if file is None or file['attachment']['message_ref'] != entry['id']:
                raise TranscriptError('Dangling or inconsistent message file reference')
    persist_group_durations(out['timeline'])
    return out


def _coalesce_input_receipts(document):
    """Reconcile an orphan occurrence with its unique mapped upload receipt.

    Message identity may change from an application occurrence to an API ID.
    The immutable upload ID, name and size prove the duplicate independently
    of row position, text or turn ID. Ambiguous bindings remain visible.
    """
    users = {entry['id'] for entry in document['timeline']
             if entry.get('kind') == 'message' and entry.get('role') == 'user'}
    groups = {}
    for file in document['files']:
        if file['kind'] == 'input' and file.get('source_id'):
            key = (file['source_id'], file['name'], file['size_bytes'])
            groups.setdefault(key, []).append(file)
    aliases = {}
    for files in groups.values():
        bound = [file for file in files if file['attachment']['message_ref'] in users]
        messages = {file['attachment']['message_ref'] for file in bound}
        turns = {file['turn_ref'] for file in bound if file['turn_ref'] is not None}
        if len(messages) != 1 or len(turns) > 1: continue
        target = next((file for file in reversed(bound) if file['turn_ref'] is not None), bound[-1])
        for file in files:
            if file is target or file['attachment']['message_ref'] not in (None, target['attachment']['message_ref']): continue
            if file['turn_ref'] is not None and target['turn_ref'] is not None and file['turn_ref'] != target['turn_ref']: continue
            aliases[file['id']] = target['id']
            if target.get('created_at') is None: target['created_at'] = file.get('created_at')
    if aliases:
        document['files'] = [file for file in document['files'] if file['id'] not in aliases]
        for entry in document['timeline']:
            entry['file_refs'] = list(dict.fromkeys(aliases.get(ref, ref) for ref in entry['file_refs']))
    return document


def merge(previous, incoming, *, authoritative=False):
    """Merge normalized snapshots by local identity, never concatenate deltas.

    An authoritative replacement must explicitly assert complete root items.
    Otherwise retain preceding turns/messages/files and replace matching IDs.
    """
    before, after = _validate(previous), _validate(incoming)
    if before['scope_id'] != after['scope_id']:
        raise TranscriptError('Cannot merge different conversations')
    if before['timeline'] and any(entry['identity'] == 'unresolved' for entry in after['timeline']):
        raise TranscriptError('Cannot merge identity-unknown items; provide stable application occurrence IDs')
    if authoritative and after['capture']['items'] != 'complete':
        raise TranscriptError('Authoritative replacement needs a complete item snapshot')
    observed_before = {entry['id']: entry for entry in before['timeline']}
    for key in ('turns', 'timeline', 'files'):
        records = {x['id']: x for x in before[key]}
        if key == 'timeline' and authoritative:
            records = {}
        if key == 'files' and authoritative:
            # A complete items response does not imply a complete artifact or
            # upload response. Do not lose cards during read-only recovery.
            for identity, file in list(records.items()):
                category = 'artifacts' if file['kind'] == 'generated' else 'input_files' if file['kind'] == 'input' else None
                if category and after['capture'][category] == 'complete':
                    records.pop(identity)
        for record in after[key]:
            if key == 'turns' and record.get('capture') == 'reference_only' and record['id'] in records:
                continue
            previous = records.get(record['id'])
            if key == 'timeline':
                observed = observed_before.get(record['id'])
                if observed and observed.get('turn_ref') == record.get('turn_ref') and 'activity_interval' not in record and 'activity_interval' in observed:
                    record['activity_interval'] = deepcopy(observed['activity_interval'])
            if (not authoritative and key == 'timeline' and previous
                    and previous.get('status') in ('completed', 'failed', 'incomplete')
                    and record.get('status') == 'in_progress'):
                continue
            records[record['id']] = record
        before[key] = list(records.values())
    for key, state in after['capture'].items():
        if state != 'not_collected':
            before['capture'][key] = state
    # A text-only incremental update must not detach previously captured files.
    # The file table is the canonical association, including late attachments.
    by_message = {entry['id']: entry for entry in before['timeline']}
    for entry in before['timeline']:
        entry['file_refs'] = []
    for file in before['files']:
        target = file['attachment']['message_ref']
        if target in by_message:
            by_message[target]['file_refs'].append(file['id'])
        elif target is not None:
            file['attachment'] = {'message_ref': None, 'basis': 'turn_only' if file['turn_ref'] else 'unresolved'}
    return _validate(_coalesce_input_receipts(before))


def migrate(document, *, scope_id, secrets=()):
    """Return a safe v2 document. Never read paths embedded in old chatbot cells."""
    if not isinstance(document, dict):
        raise TranscriptError('History must be a JSON object')
    version = document.get('history_format')
    if version is not None and version != {'name': 'chuanhu', 'version': FORMAT_VERSION}:
        raise UnsupportedVersion('Unsupported history version; preserve the source file')
    if 'agent_transcript' in document:
        transcript = _validate(document['agent_transcript'], secrets=secrets)
    else:
        history = document.get('history')
        if not isinstance(history, list) or len(history) > MAX_RECORDS:
            raise TranscriptError('Invalid legacy history')
        items = []
        for index, item in enumerate(history):
            if isinstance(item, str):
                role, text = ('user' if index % 2 == 0 else 'assistant'), item
            elif isinstance(item, dict) and item.get('role') in ('user', 'assistant') and isinstance(item.get('content'), str):
                role, text = item['role'], item['content']
            else:
                raise TranscriptError('Invalid legacy message')
            items.append({'id': None, 'type': 'message', 'role': role, 'content': [{'type': 'text', 'text': text}]})
        transcript = normalize(items, scope_id=scope_id, secrets=secrets)
        rows = document.get('chatbot', [])
        if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
            raise TranscriptError('Invalid legacy chatbot')
        for index, row in enumerate(rows):
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise TranscriptError('Invalid legacy chatbot row')
            for column, cell in enumerate(row):
                if isinstance(cell, (list, tuple)) and 1 <= len(cell) <= 2 and isinstance(cell[0], str):
                    # Display-only basename. No filesystem access or permission.
                    transcript['files'].append({'id': _id(scope_id, 'file', ['legacy', index, column]), 'source_id': None,
                                                'kind': 'legacy', 'turn_ref': None, 'name': _text(_filename(cell[0]), secrets=secrets), 'size_bytes': None, 'created_at': None,
                                                'availability': 'metadata_only', 'attachment': {'message_ref': None, 'basis': 'unresolved'}})
    transcript = _coalesce_input_receipts(transcript)
    out = {'history_format': {'name': 'chuanhu', 'version': FORMAT_VERSION}, 'agent_transcript': transcript}
    for key in _LEGACY_FIELDS:
        if key in document:
            # Agent history metadata is display-only and carries no legacy
            # model/connection configuration or authority.
            out[key] = {} if key == 'metadata' else _text(document[key], secrets=secrets) if key == 'system' and isinstance(document[key], str) else sanitize(document[key], secrets=secrets)[0]
    out['history'], out['chatbot'] = legacy_projection(transcript)
    return out


def serialize(document, *, secrets=()):
    """Serialize known v2 fields; refusal prevents silent future-version loss."""
    scope = document.get('agent_transcript', {}).get('scope_id') if isinstance(document, dict) else None
    out = migrate(document, scope_id=scope, secrets=secrets)
    wire = json.dumps(out, ensure_ascii=False, allow_nan=False, indent=2)
    if len(wire.encode()) > MAX_DOCUMENT_BYTES:
        raise TranscriptError('History exceeds the document size limit')
    return wire


def loads(wire, *, scope_id, secrets=(), imported=False):
    if not isinstance(wire, str) or len(wire.encode()) > MAX_DOCUMENT_BYTES:
        raise TranscriptError('Invalid or oversized history JSON')
    try:
        document = migrate(json.loads(wire), scope_id=scope_id, secrets=secrets)
        if imported:
            if not _source_id(scope_id, secrets):
                raise TranscriptError('Imported history needs a fresh local scope')
            transcript = document['agent_transcript']
            remap = {record['id']: _id(scope_id, kind, record['id'])
                     for collection, kind in (('timeline', 'entry'), ('turns', 'turn'), ('files', 'file'))
                     for record in transcript[collection]}
            for collection in ('timeline', 'turns', 'files'):
                for record in transcript[collection]:
                    record['id'] = remap[record['id']]
                    if 'turn_ref' in record and record['turn_ref'] is not None:
                        record['turn_ref'] = remap[record['turn_ref']]
                    if 'file_refs' in record:
                        record['file_refs'] = [remap[ref] for ref in record['file_refs']]
                    if 'attachment' in record and record['attachment']['message_ref']:
                        record['attachment']['message_ref'] = remap[record['attachment']['message_ref']]
            transcript['scope_id'] = scope_id
        return document
    except (json.JSONDecodeError, RecursionError) as error:
        raise TranscriptError('Invalid history JSON') from error


def render_input(document, *, resolve_file=None):
    """Return raw display records/cards before any HTML formatting.

    A trusted owner/session-aware resolver receives ONLY the local file ID.
    It may return an application-owned download handle, never a JSON path.
    This function does not call a network, filesystem, worker or UI.
    """
    transcript = _validate(document['agent_transcript'])
    files = {x['id']: deepcopy(x) for x in transcript['files']}
    for file in files.values():
        file['download'] = None
        if resolve_file is not None:
            handle = resolve_file(file['id'])
            if isinstance(handle, str) and handle and len(handle) <= 512 and not re.search(r'[\x00-\x20]', handle):
                file['download'] = handle
    timeline = deepcopy(transcript['timeline'])
    attached = set()
    for entry in timeline:
        entry['files'] = [files[ref] for ref in entry.pop('file_refs')]
        attached.update(f['id'] for f in entry['files'])
    return {'scope_id': transcript['scope_id'], 'timeline': timeline,
            'turn_files': [f for ref, f in files.items() if ref not in attached],
            'turns': deepcopy(transcript['turns']), 'capture': deepcopy(transcript['capture'])}
