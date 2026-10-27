"""Pure view projection for associating Agent files with message bubbles.

Official session/message IDs identify bubbles. Turn IDs identify file-only and
provisional bubbles until a message item exists. Ambiguous or absent historical
messages get their own view-only bubble instead of borrowing a nearby answer.
Neither projection nor rendering mutates the caller's raw conversation.
"""
from base64 import b64decode, b64encode
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import html
import json
import re
from typing import Callable, Dict, List, Set
from modules.agent.file_icons import file_icon, file_size_label, file_type_label, split_filename


@dataclass
class MessageFileProjection:
    rows: List[list]
    row_anchors: Dict[int, str]
    artifact_anchors: Dict[str, str]
    view_only_rows: Set[int]
    conversation_id: str
    unresolved_artifacts: Dict[str, str] = field(default_factory=dict)
    _original_rows: List[list] = field(default_factory=list, repr=False)

    user_files: Dict[int, list] = field(default_factory=dict)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(value.encode('utf-8', errors='surrogatepass')).hexdigest()


def _anchor(scope, kind, identifier):
    return 'am-' + _digest(_json([scope, kind, identifier]))


def _identifier(value):
    return value if isinstance(value, str) and value else None


def _is_file_cell(value):
    """Recognize raw Gradio file cells structurally, without opening paths."""
    return (isinstance(value, (list, tuple)) and len(value) in (1, 2)
            and isinstance(value[0], str) and bool(value[0])
            and (len(value) == 1 or value[1] is None or isinstance(value[1], str)))


def _is_text_cell(value):
    return value is None or isinstance(value, str)


def group_turn_messages(items):
    """One logical reply per root turn; retain original IDs in cloud storage."""
    grouped = []
    for item in items:
        if (grouped and item.get('role') == 'assistant' and item.get('turn_id')
                and grouped[-1].get('role') == 'assistant'
                and grouped[-1].get('turn_id') == item['turn_id']):
            if item['content']:
                grouped[-1]['content'] += ('\n\n' if grouped[-1]['content'] else '') + item['content']
        else:
            grouped.append(deepcopy(item))
    return grouped


def _cloud_rows(items):
    unique = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        identifier = _identifier(item.get('id'))
        if identifier and item.get('role') in ('user', 'assistant') and isinstance(item.get('content'), str):
            unique[identifier] = item
    rows = []
    for item in group_turn_messages(unique.values()):
        if item['role'] == 'user':
            rows.append({'user': item, 'assistant': None})
        elif rows and rows[-1]['assistant'] is None:
            rows[-1]['assistant'] = item
        else:
            rows.append({'user': None, 'assistant': item})
    return rows


def _match_score(source, row, weight):
    user, assistant = source['user'], source['assistant']
    # Input-file manifests are intentionally projected to clean user text by
    # the model, so exact user text strengthens a match but is not required.
    if (user is None) != (row[0] is None):
        return None
    if assistant is None:
        if row[1] is not None:
            return None
    elif row[1] != assistant['content']:
        return None
    return weight + int(user is not None and user['content'] == row[0])


def _align_rows(source, raw, source_indices, raw_indices):
    """Return only row pairs shared by every optimal monotonic alignment.

    Authoritative histories and an unambiguous appended preview have linear
    paths. Other subsets and previews use sequence alignment; indistinguishable
    repeated rows remain unassigned rather than borrowing a historical message.
    """
    # Adopted ordinary histories may include native Gradio image/file rows.
    # They are preserved in the view, but have no cloud text-message identity.
    raw_indices = [j for j in raw_indices if all(_is_text_cell(value) for value in raw[j])]
    m, n = len(source_indices), len(raw_indices)
    if not m or not n:
        return {}
    weight = min(m, n) + 1
    source_users = {source[i]['user']['content'] for i in source_indices if source[i]['user'] is not None}
    raw_users = {raw[j][0] for j in raw_indices if raw[j][0] is not None}

    def score(i, j):
        user = source[i]['user']
        if user is not None and user['content'] != raw[j][0]:
            # A known exact user identity elsewhere is evidence against this
            # pair. Preserve projected-manifest matches only where they do not
            # contradict an available exact user-text match.
            if user['content'] in raw_users or raw[j][0] in source_users:
                return None
        return _match_score(source[i], raw[j], weight)

    if m <= n and all(score(i, j) is not None for i, j in zip(source_indices, raw_indices)):
        if m == n:
            return dict(zip(source_indices, raw_indices))
        # Before a new turn ID arrives, raw history commonly contains every
        # official row plus a new preview. If no suffix row can match *any*
        # source row, matching all m source rows forces the unique prefix
        # alignment. Index candidate signatures to prove this in O(m + n),
        # without allocating the dynamic-programming matrices on each frame.
        candidate_users, flexible_signatures = {}, set()
        for i in source_indices:
            user, assistant = source[i]['user'], source[i]['assistant']
            signature = (user is None, None if assistant is None else assistant['content'])
            users = candidate_users.setdefault(signature, set())
            if user is not None:
                users.add(user['content'])
                if user['content'] not in raw_users:
                    flexible_signatures.add(signature)

        def has_candidate(j):
            user, assistant = raw[j]
            signature = (user is None, assistant)
            if signature not in candidate_users:
                return False
            if user is None or user in candidate_users[signature]:
                return True
            return user not in source_users and signature in flexible_signatures

        if not any(has_candidate(j) for j in raw_indices[m:]):
            return dict(zip(source_indices, raw_indices))
    return _align_rows_dynamic(source_indices, raw_indices, score)


def _align_rows_dynamic(source_indices, raw_indices, score):
    """Resolve genuinely uncertain alignments, retaining all optimal paths."""
    m, n = len(source_indices), len(raw_indices)
    scores = [[score(i, j) for j in raw_indices] for i in source_indices]
    forward = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            best = max(forward[i][j + 1], forward[i + 1][j])
            if scores[i][j] is not None:
                best = max(best, forward[i][j] + scores[i][j])
            forward[i + 1][j + 1] = best
    backward = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            best = max(backward[i + 1][j], backward[i][j + 1])
            if scores[i][j] is not None:
                best = max(best, scores[i][j] + backward[i + 1][j + 1])
            backward[i][j] = best
    optimum = forward[m][n]
    choices = [set() for _ in range(m)]
    raw_choices = [set() for _ in range(n)]
    skipped_source, skipped_raw = set(), set()
    for i in range(m + 1):
        for j in range(n + 1):
            if i < m and forward[i][j] + backward[i + 1][j] == optimum:
                skipped_source.add(i)
            if j < n and forward[i][j] + backward[i][j + 1] == optimum:
                skipped_raw.add(j)
            if i < m and j < n and scores[i][j] is not None:
                if forward[i][j] + scores[i][j] + backward[i + 1][j + 1] == optimum:
                    choices[i].add(j)
                    raw_choices[j].add(i)
    result = {}
    for i, options in enumerate(choices):
        if len(options) == 1 and i not in skipped_source:
            j = next(iter(options))
            if len(raw_choices[j]) == 1 and j not in skipped_raw:
                result[source_indices[i]] = raw_indices[j]
    return result


def project_message_files(rows, cloud_items, artifacts, *, session_id, conversation_id,
                          current_turn_id=None, answer_row=None, input_messages=None, pending_input_files=()):
    """Build a raw view plus stable text-assistant and artifact anchor maps.

    ``answer_row`` is an explicit raw-row index for the current turn, supplied
    by the model while its newest answer has not yet reached cloud history.
    Artifacts from another session are ignored. Missing or ambiguous history
    produces a deterministic, view-only placeholder; artifact order and names
    never decide ownership. Missing artifact session IDs inherit this scope.
    Native Gradio file cells pass through without reading or resolving paths.
    """
    if not isinstance(conversation_id, str):
        raise TypeError('conversation_id must be a string')
    original = deepcopy(list(rows or []))
    if any(not isinstance(row, (list, tuple)) or len(row) != 2
           or any(not _is_text_cell(value) and not _is_file_cell(value) for value in row)
           for row in original):
        raise TypeError('rows must contain pairs of string, None, or native file cells')
    original = [list(row) for row in original]
    projected = deepcopy(original)
    source = _cloud_rows(cloud_items)
    scope = ['session', session_id] if _identifier(session_id) else ['conversation', conversation_id]
    assistant_turns, user_turns = {}, {}
    for i, source_row in enumerate(source):
        for role, by_turn in (('user', user_turns), ('assistant', assistant_turns)):
            item = source_row[role]
            if item and _identifier(item.get('turn_id')):
                by_turn[item['turn_id']] = i
    current_turn_id = _identifier(current_turn_id)
    current_row = (answer_row if type(answer_row) is int and 0 <= answer_row < len(original)
                   and current_turn_id and _is_text_cell(original[answer_row][1]) else None)
    current_source = assistant_turns.get(current_turn_id, user_turns.get(current_turn_id)) if current_row is not None else None
    if current_source is not None:
        # Explicit model state also covers changed streaming text and a local
        # single-answer preview that later expands to several assistant items.
        aligned = _align_rows(source, original, list(range(current_source)), list(range(current_row)))
        aligned[current_source] = current_row
        aligned.update(_align_rows(source, original, list(range(current_source + 1, len(source))),
                                   list(range(current_row + 1, len(original)))))
    else:
        aligned = _align_rows(source, original, list(range(len(source))),
                              [i for i in range(len(original)) if i != current_row])
    anchors = {}
    message_rows = {}
    for i, j in aligned.items():
        item = source[i]['assistant']
        if item is not None:
            key = _anchor(scope, 'message', item['id'])
            anchors[j] = key
            message_rows[item['id']] = j
    if current_row is not None and current_row not in anchors:
        anchors[current_row] = _anchor(scope, 'turn', current_turn_id)

    projection = MessageFileProjection(projected, anchors, {}, set(), conversation_id, {}, original)
    for source_index, row_index in aligned.items():
        user = source[source_index]['user']
        entry = (input_messages or {}).get(_digest(user['content'])) if user else None
        if isinstance(entry, dict) and entry.get('files'): projection.user_files[row_index] = deepcopy(entry['files'])
    if answer_row is not None and pending_input_files and answer_row not in projection.user_files:
        projection.user_files[answer_row] = deepcopy(pending_input_files)
    grouped = {}
    conflicting = set()
    for record in artifacts or []:
        if not isinstance(record, dict) or not _identifier(record.get('id')):
            continue
        artifact_id = record['id']
        record_session = _identifier(record.get('session_id'))
        if record_session and record_session != session_id:
            continue
        turn = _identifier(record.get('turn_id'))
        if artifact_id in grouped and grouped[artifact_id] != turn:
            conflicting.add(artifact_id)
        grouped[artifact_id] = turn
    placeholders = {}
    for artifact_id in sorted(grouped):
        if artifact_id in conflicting:
            projection.unresolved_artifacts[artifact_id] = 'conflicting artifact turn IDs'
            continue
        turn = grouped[artifact_id]
        target = None
        if turn in assistant_turns:
            source_index = assistant_turns[turn]
            item = source[source_index]['assistant']
            key = _anchor(scope, 'message', item['id'])
            target = message_rows.get(item['id'])
            reason = 'assistant message is absent or ambiguous in displayed history'
        elif turn is not None and turn == current_turn_id and current_row is not None:
            target = current_row
            key = anchors[current_row]
            reason = ''
        elif turn in user_turns:
            key = _anchor(scope, 'turn', turn)
            target = aligned.get(user_turns[turn])
            if target is not None and original[target][1] is not None:
                target = None
            reason = 'file-only user message is absent or ambiguous in displayed history'
        elif turn is not None:
            key = _anchor(scope, 'turn', turn)
            reason = 'turn is absent from displayed cloud history'
        else:
            key = _anchor(scope, 'artifact', artifact_id)
            reason = 'artifact has no turn ID'
        if target is None:
            placeholders[key] = True
            projection.unresolved_artifacts[artifact_id] = reason
        else:
            anchors[target] = key
            if projected[target][1] is None:
                projected[target][1] = ''
        projection.artifact_anchors[artifact_id] = key
    for key in sorted(placeholders):
        index = len(projected)
        projected.append([None, ''])
        original.append([None, None])
        projection.view_only_rows.add(index)
        anchors[index] = key
    # Legacy/local text has no server identity. Its content-derived view key is
    # deliberately never used to assign a file without an explicit turn match.
    occurrences = {}
    for i, row in enumerate(projected):
        if isinstance(row[1], str) and i not in anchors:
            identity = _json(row)
            occurrence = occurrences.get(identity, 0)
            occurrences[identity] = occurrence + 1
            anchors[i] = _anchor(scope, 'local', [identity, occurrence])
    return projection


# Only this exact, suffix-positioned marker is a decoding candidate. Rebuilding
# it after validation rejects additional attributes, malformed JSON and markers
# whose rendered prefix or conversation no longer matches.
_MARKER = re.compile(
    r'<span class="(?P<class>agent-message-anchor|agent-message-raw)" hidden="hidden" '
    r'data-message-key="(?P<key>am-[0-9a-f]{64})" '
    r'data-conversation-id="(?P<conversation>[^"]*)" '
    r'data-agent-message-cell="(?P<role>user|assistant)" '
    r'data-agent-message-raw="(?P<payload>[A-Za-z0-9+/]*={0,2})"></span>\Z'
)
_PAYLOAD_FIELDS = {'v', 'conversation', 'key', 'role', 'raw', 'view_only', 'rendered_sha256'}


def _marker(payload):
    encoded = b64encode(_json(payload).encode('utf-8', errors='surrogatepass')).decode('ascii')
    marker_class = 'agent-message-anchor' if payload['role'] == 'assistant' else 'agent-message-raw'
    return ('<span class="' + marker_class + '" hidden="hidden" data-message-key="' + payload['key']
            + '" data-conversation-id="' + html.escape(payload['conversation'], quote=True)
            + '" data-agent-message-cell="' + payload['role']
            + '" data-agent-message-raw="' + encoded + '"></span>')


def _body_segment(markup, raw, conversation, key, position, *, copy_only=False):
    # Independent exact body source for copy when the view suffix is absent.
    # This carries no decoder authority; the strict v1 suffix remains unchanged.
    encoded = b64encode(_json({'v': 1, 'conversation': conversation, 'key': key,
                               'position': position, 'raw': raw}).encode('utf-8', errors='surrogatepass')).decode('ascii')
    attributes = (' data-conversation-id="'+html.escape(conversation, quote=True)
                  +'" data-message-key="'+key+'" data-agent-body-raw="'+encoded+'"')
    if copy_only:
        return '<span class="agent-body-copy-source" hidden="hidden"'+attributes+'></span>'
    return '<div class="agent-body-segment"'+attributes+'>'+markup+'</div>'


def render_projection(projection, format_user: Callable[[str], str], format_assistant: Callable[[str], str]):
    """Format raw cells, then append reversible metadata outside copy markup."""
    result = []
    for index, row in enumerate(projection.rows):
        rendered = []
        original = projection._original_rows[index]
        key = projection.row_anchors.get(index) or _anchor(['conversation', projection.conversation_id], 'raw-user', original)
        for cell, (role, formatter) in enumerate((('user', format_user), ('assistant', format_assistant))):
            value = row[cell]
            if value is None or _is_file_cell(value):
                rendered.append(deepcopy(value))
                continue
            prefix = formatter(value)
            segments=getattr(projection,'cell_segments',{}).get((index,cell))
            if segments is not None:
                # Each body keeps its own raw/render pair beside inert activity.
                raw=re.search(r'<div class="raw-message hideM">.*?</div>',prefix,re.S)
                rendered_parts=[]
                visible_sources=[(position, segment) for position, segment in enumerate(segments)
                                 if 'text' not in segment or segment['text'].strip()]
                visible_segments=[segment for _, segment in visible_sources]
                for position, segment in enumerate(visible_segments):
                    if 'text' in segment:
                        formatted=formatter(segment['text'])
                        rendered_parts.append(_body_segment(formatted, segment['text'], projection.conversation_id, key, visible_sources[position][0]))
                    else:
                        # Body adjacency comes from visible text segments, not
                        # hidden copy payloads, anchors or Markdown tag shape.
                        markup=segment['markup']
                        root='<div class="agent-history-activity">'
                        first,last=markup.find(root),markup.rfind(root)
                        if first>=0:
                            if position+1<len(visible_segments) and 'text' in visible_segments[position+1]:
                                markup=markup[:last]+root[:-1]+' data-body-after="true">'+markup[last+len(root):]
                            if position and 'text' in visible_segments[position-1]:
                                markup=markup[:first]+markup[first:].replace(root[:-1],root[:-1]+' data-body-before="true"',1)
                        rendered_parts.append(markup)
                # Whitespace is invisible layout, but still canonical body.
                # Keep its copy sources outside the activity adjacency chain.
                copy_only_sources=[_body_segment('', segment['text'], projection.conversation_id, key, position, copy_only=True)
                                   for position, segment in enumerate(segments)
                                   if 'text' in segment and not segment['text'].strip()]
                prefix=''.join(rendered_parts)+''.join(copy_only_sources)
                if role == 'assistant' and '<div class="md-message">' not in prefix:
                    # Keep the original formatter's structural idempotence
                    # contract in this trusted generation path. The body is
                    # empty and hidden: it creates no text, layout or spacing.
                    # Never infer trusted HTML from a client-supplied hash.
                    prefix += '<div class="agent-format-receipt hideM" hidden>'+(raw.group(0) if raw else '')+'<div class="md-message"></div></div>'
            elif role == 'assistant' and isinstance(original[cell], str):
                prefix = _body_segment(prefix, original[cell], projection.conversation_id, key, 0)
            prefix += getattr(projection, 'cell_details', {}).get((index, cell), '')
            if role == 'user' and projection.user_files.get(index):
                cards = []
                for file in projection.user_files[index]:
                    name = str(file.get('name', '附件'))
                    basename = split_filename(name)[0]
                    meta = file_type_label(name) + ' · ' + file_size_label(file.get('size'))
                    cards.append('<span class="agent-input-card agent-file-card">' + file_icon(name) + '<span class="agent-input-card-text" data-file-part="content"><span class="agent-input-name" data-file-part="name" title="' + html.escape(name, quote=True) + '"><span data-file-part="basename">' + html.escape(basename) + '</span></span><span class="agent-input-meta" data-file-part="meta">' + html.escape(meta) + '</span></span></span>')
                prefix = '<div class="agent-user-file-source" hidden>' + ''.join(cards) + '</div>' + prefix
            if not isinstance(prefix, str):
                raise TypeError('message formatters must return strings')
            payload = {'v': 1, 'conversation': projection.conversation_id, 'key': key, 'role': role,
                       'raw': original[cell], 'view_only': index in projection.view_only_rows,
                       'rendered_sha256': _digest(prefix)}
            rendered.append(prefix + _marker(payload))
        result.append(rendered)
    return result


def _decode_cell(value, conversation_id, role):
    if not isinstance(value, str):
        return deepcopy(value), None
    match = _MARKER.search(value)
    if match is None:
        return value, None
    try:
        payload = json.loads(b64decode(match['payload'], validate=True).decode('utf-8', errors='surrogatepass'))
        if not isinstance(payload, dict) or set(payload) != _PAYLOAD_FIELDS:
            return value, None
        if type(payload['v']) is not int or payload['v'] != 1:
            return value, None
        if payload['conversation'] != conversation_id or not isinstance(payload['conversation'], str):
            return value, None
        if payload['role'] != role or payload['key'] != match['key']:
            return value, None
        if payload['raw'] is not None and not isinstance(payload['raw'], str):
            return value, None
        if type(payload['view_only']) is not bool or not isinstance(payload['rendered_sha256'], str):
            return value, None
        if payload['rendered_sha256'] != _digest(value[:match.start()]):
            return value, None
        if _marker(payload) != match.group():
            return value, None
        return payload['raw'], payload
    except (ValueError, UnicodeError, TypeError, KeyError):
        return value, None


def decode_rows(rows, conversation_id):
    """Recover raw cells for this conversation; preserve all unmarked input.

    Only a valid assistant marker can remove a view-only row, and then only
    when the row still has the exact empty shape generated by the projection.
    """
    result = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            result.append(deepcopy(row))
            continue
        user, user_meta = _decode_cell(row[0], conversation_id, 'user')
        assistant, assistant_meta = _decode_cell(row[1], conversation_id, 'assistant')
        if (assistant_meta and assistant_meta['view_only'] and assistant is None
                and row[0] is None and user_meta is None):
            continue
        result.append([user, assistant])
    return result
