"""Offline tests of artifact ownership and reversible message-only view HTML."""
from base64 import b64decode, b64encode
from copy import deepcopy
import json
import re

import pytest

from modules.agent.message_files import decode_rows, project_message_files, render_projection


def item(identifier, role, content, turn):
    return dict(id=identifier, role=role, content=content, turn_id=turn)


def artifact(identifier, turn, session='session', **extra):
    return dict(id=identifier, turn_id=turn, session_id=session, name='same.txt', **extra)


def project(rows, items=(), artifacts=(), **kwargs):
    return project_message_files(rows, items, artifacts, session_id=kwargs.pop('session_id', 'session'),
                                 conversation_id=kwargs.pop('conversation_id', 'conversation'), **kwargs)


def user_format(raw):
    return '<div class="user-message">' + raw + '</div>'


def assistant_format(raw):
    return '<div class="raw-message hideM">' + raw + '</div><div class="md-message">' + raw + '</div>'


def render(projection):
    return render_projection(projection, user_format, assistant_format)


def two_turns():
    return [item('u1', 'user', 'first?', 't1'), item('a1', 'assistant', 'first!', 't1'),
            item('u2', 'user', 'second?', 't2'), item('a2', 'assistant', 'second!', 't2')]


def test_official_turns_bind_same_named_files_to_their_own_answers():
    rows = [['first?', 'first!'], ['second?', 'second!']]
    records = [artifact('file-2', 't2'), artifact('file-1', 't1')]
    result = project(rows, two_turns(), records)
    assert result.rows == rows
    assert result.artifact_anchors == {'file-1': result.row_anchors[0], 'file-2': result.row_anchors[1]}
    assert result.row_anchors[0] != result.row_anchors[1]
    assert not result.view_only_rows
    assert not result.unresolved_artifacts


def test_same_turn_multiple_assistants_share_one_logical_reply():
    items = [item('u', 'user', 'question', 'turn'), item('a1', 'assistant', 'working', 'turn'),
             item('a2', 'assistant', 'finished', 'turn')]
    result = project([['question', 'working\n\nfinished']], items, [artifact('file', 'turn')])
    assert result.artifact_anchors['file'] == result.row_anchors[0]
    assert len(result.rows) == 1 and not result.view_only_rows


def test_attachment_manifest_user_text_can_differ_from_displayed_user():
    items = [item('u1', 'user', 'input file manifest and question', 't1'),
             item('a1', 'assistant', 'first!', 't1'),
             item('u2', 'user', 'reference history and second question', 't2'),
             item('a2', 'assistant', 'second!', 't2')]
    result = project([['first?', 'first!'], ['second?', 'second!']], items, [artifact('f', 't2')])
    assert result.artifact_anchors['f'] == result.row_anchors[1]
    assert not result.view_only_rows


def test_message_identity_survives_restoration_conversation_change_and_history_shrink():
    records = [artifact('f', 't2')]
    before = project([['first?', 'first!'], ['second?', 'second!']], two_turns(), records)
    restored = project([['second?', 'second!']], two_turns()[2:], records, conversation_id='restored')
    shortened_view = project([['second?', 'second!']], two_turns(), records)
    assert before.artifact_anchors['f'] == restored.artifact_anchors['f'] == shortened_view.artifact_anchors['f']
    assert shortened_view.artifact_anchors['f'] == shortened_view.row_anchors[0]
    assert not shortened_view.view_only_rows


def test_different_sessions_never_reuse_message_or_turn_anchors():
    one = project([['first?', 'first!']], two_turns()[:2], [artifact('f', 't1')])
    two = project([['first?', 'first!']], two_turns()[:2], [artifact('f', 't1', 'another')], session_id='another')
    assert one.artifact_anchors['f'] != two.artifact_anchors['f']
    one_file_only = project([], [], [artifact('f', 't')])
    two_file_only = project([], [], [artifact('f', 't', 'another')], session_id='another')
    assert one_file_only.artifact_anchors['f'] != two_file_only.artifact_anchors['f']
    foreign = project([['first?', 'first!']], two_turns(), [artifact('f', 't1', 'foreign')])
    assert not foreign.artifact_anchors and not foreign.view_only_rows


def test_file_only_turn_uses_corresponding_user_none_slot_and_roundtrips():
    rows = [['make a file', None], ['later question', 'later answer']]
    items = [item('u1', 'user', 'manifest', 't1'), item('u2', 'user', 'later question', 't2'),
             item('a2', 'assistant', 'later answer', 't2')]
    result = project(rows, items, [artifact('file', 't1')])
    assert result.rows == [['make a file', ''], ['later question', 'later answer']]
    assert result.artifact_anchors['file'] == result.row_anchors[0]
    assert not result.view_only_rows
    assert decode_rows(render(result), 'conversation') == rows


def test_current_turn_explicit_row_supports_unsynced_answer_and_file_only():
    rows = [['first?', 'first!'], ['make a file', None]]
    result = project(rows, two_turns()[:2], [artifact('old', 't1'), artifact('new', 't2')],
                     current_turn_id='t2', answer_row=1)
    assert result.artifact_anchors['old'] == result.row_anchors[0]
    assert result.artifact_anchors['new'] == result.row_anchors[1]
    assert result.rows[1] == ['make a file', '']
    assert decode_rows(render(result), 'conversation') == rows
    assert not result.view_only_rows


def test_current_turn_keeps_official_message_anchor_while_streaming_text_changes():
    items = [item('u', 'user', 'question', 't'), item('a', 'assistant', 'partial', 't')]
    before = project([['question', 'partial']], items, [artifact('file', 't')])
    streaming = project([['question', 'partial with more tokens']], items, [artifact('file', 't')],
                        current_turn_id='t', answer_row=0)
    assert streaming.artifact_anchors['file'] == before.artifact_anchors['file']
    assert streaming.artifact_anchors['file'] == streaming.row_anchors[0]


def test_unknown_turns_and_missing_turns_get_independent_deterministic_placeholders():
    rows = [['first?', 'first!'], ['second?', 'second!']]
    records = [artifact('z', 'unknown'), artifact('a', 'unknown'), artifact('no-turn', None)]
    before = deepcopy((rows, records))
    one = project(rows, two_turns(), records)
    two = project(rows, two_turns(), list(reversed(records)))
    assert one.rows == two.rows and one.row_anchors == two.row_anchors
    assert one.artifact_anchors == two.artifact_anchors
    assert len(one.view_only_rows) == 2
    assert one.artifact_anchors['z'] == one.artifact_anchors['a']
    assert one.artifact_anchors['no-turn'] != one.artifact_anchors['a']
    assert one.artifact_anchors['a'] not in (one.row_anchors[0], one.row_anchors[1])
    assert decode_rows(render(one), 'conversation') == rows
    assert (rows, records) == before


def test_ambiguous_shortened_repeated_answers_do_not_borrow_a_historical_bubble():
    items = [item('u1', 'user', 'repeated?', 't1'), item('a1', 'assistant', 'same', 't1'),
             item('u2', 'user', 'repeated?', 't2'), item('a2', 'assistant', 'same', 't2')]
    result = project([['repeated?', 'same']], items, [artifact('one', 't1'), artifact('two', 't2')])
    assert len(result.view_only_rows) == 2
    assert result.artifact_anchors['one'] != result.artifact_anchors['two']
    assert result.row_anchors[0] not in result.artifact_anchors.values()
    # A full authoritative snapshot disambiguates the very same text by order.
    complete = project([['repeated?', 'same'], ['repeated?', 'same']], items,
                       [artifact('one', 't1'), artifact('two', 't2')])
    assert complete.artifact_anchors['one'] == complete.row_anchors[0]
    assert complete.artifact_anchors['two'] == complete.row_anchors[1]


def test_exact_user_text_disambiguates_repeated_assistant_content_when_available():
    items = [item('u1', 'user', 'one?', 't1'), item('a1', 'assistant', 'same', 't1'),
             item('u2', 'user', 'two?', 't2'), item('a2', 'assistant', 'same', 't2')]
    result = project([['two?', 'same']], items, [artifact('f', 't2')])
    assert result.artifact_anchors['f'] == result.row_anchors[0]
    assert not result.view_only_rows


def test_last_assistant_missing_from_view_does_not_attach_to_earlier_same_turn_answer():
    items = [item('u', 'user', 'question', 't'), item('a1', 'assistant', 'working', 't'),
             item('a2', 'assistant', 'done', 't')]
    result = project([['question', 'working']], items, [artifact('f', 't')])
    assert result.view_only_rows == {1}
    assert result.artifact_anchors['f'] == result.row_anchors[1]
    assert result.artifact_anchors['f'] != result.row_anchors[0]


def test_file_only_user_does_not_claim_an_assistant_from_a_different_turn():
    items = [item('u', 'user', 'question', 'file-only'), item('a', 'assistant', 'unrelated', 'other')]
    result = project([['question', 'unrelated']], items, [artifact('f', 'file-only')])
    assert result.view_only_rows == {1}
    assert result.artifact_anchors['f'] != result.row_anchors[0]


def test_conflicting_duplicate_artifact_ids_are_not_assigned_by_record_order():
    records = [artifact('same-id', 't1'), artifact('same-id', 't2')]
    one = project([['first?', 'first!'], ['second?', 'second!']], two_turns(), records)
    two = project([['first?', 'first!'], ['second?', 'second!']], two_turns(), reversed(records))
    assert one.artifact_anchors == two.artifact_anchors == {}
    assert one.unresolved_artifacts == two.unresolved_artifacts == {'same-id': 'conflicting artifact turn IDs'}


@pytest.mark.parametrize('raw', [None, '', 'plain', '<b>HTML & \'quoted\'</b>',
                                 '你好 👩🏽\u200d💻\n\n```html\n<span>copy</span>\n```',
                                 '</span><span class="agent-message-anchor" hidden></span>'])
def test_html_emoji_empty_and_none_cells_roundtrip_exactly(raw):
    rows = [[raw, raw], [None, raw], [raw, None]]
    result = project(rows)
    rendered = render(result)
    assert decode_rows(rendered, 'conversation') == rows
    assert rows == result.rows


def test_render_calls_each_converter_once_and_marker_is_outside_copy_region():
    calls = []
    def converter(role):
        def convert(value):
            calls.append((role, value))
            return '<div class="raw-message">' + value + '</div>'
        return convert
    result = project([['question', 'answer']])
    rendered = render_projection(result, converter('user'), converter('assistant'))
    assert calls == [('user', 'question'), ('assistant', 'answer')]
    assert '<div class="raw-message">answer</div></div><span class="agent-message-anchor"' in rendered[0][1]
    assert rendered[0][1].startswith('<div class="agent-body-segment"')
    assert rendered[0][0].startswith('<div class="raw-message">question</div><span class="agent-message-raw"')
    assert 'data-message-key="' + result.row_anchors[0] + '"' in rendered[0][1]


def test_foreign_conversation_markers_and_unmarked_rows_are_preserved():
    rendered = render(project([['raw <i>user</i>', 'answer']]))
    assert decode_rows(rendered, 'other-conversation') == rendered
    unmarked = [[None, '<div class="md-message">ordinary</div>'], ['q', None]]
    assert decode_rows(unmarked, 'conversation') == unmarked


def test_view_only_rows_are_not_removed_for_foreign_conversation_or_modified_user():
    rendered = render(project([], [], [artifact('f', 'missing')]))
    assert len(decode_rows(rendered, 'wrong')) == 1
    rendered[0][0] = 'user added content'
    assert decode_rows(rendered, 'conversation') == [['user added content', None]]


def test_modified_prefix_marker_attributes_or_cell_role_are_not_decoded():
    rendered = render(project([['question', 'answer']]))
    original = rendered[0][1]
    variants = ['changed' + original, original.replace('hidden="hidden"', 'hidden'),
                original + 'trailing text', original.replace('agent-message-anchor', 'agent-message-raw')]
    for variant in variants:
        assert decode_rows([[None, variant]], 'conversation') == [[None, variant]]
    assert decode_rows([[original, None]], 'conversation') == [[original, None]]


def rewrite_payload(value, changes):
    encoded = re.search(r'data-agent-message-raw="([^"]+)"', value).group(1)
    payload = json.loads(b64decode(encoded))
    payload.update(changes)
    replacement = b64encode(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode()).decode()
    return value.replace(encoded, replacement)


@pytest.mark.parametrize('changes', [{'raw': {'not': 'text'}}, {'raw': 4}, {'v': True},
                                    {'view_only': 1}, {'unexpected': 'field'},
                                    {'rendered_sha256': []}, {'conversation': ['conversation']}])
def test_decoder_checks_payload_schema_and_types(changes):
    rendered = render(project([['question', 'answer']]))
    malformed = rewrite_payload(rendered[0][1], changes)
    assert decode_rows([[None, malformed]], 'conversation') == [[None, malformed]]


def test_malformed_base64_json_and_noncanonical_payload_are_preserved():
    rendered = render(project([['question', 'answer']]))[0][1]
    encoded = re.search(r'data-agent-message-raw="([^"]+)"', rendered).group(1)
    for replacement in ('x', b64encode(b'not json').decode(), b64encode(b'[]').decode(),
                        b64encode(json.dumps(json.loads(b64decode(encoded)), indent=2).encode()).decode()):
        malformed = rendered.replace(encoded, replacement)
        assert decode_rows([[None, malformed]], 'conversation') == [[None, malformed]]


def test_conversation_identifier_is_escaped_and_validated():
    conversation = 'conversation"<&\'👋'
    rows = [['q', 'a']]
    rendered = render(project(rows, conversation_id=conversation))
    assert 'data-conversation-id="conversation&quot;&lt;&amp;&#x27;👋"' in rendered[0][1]
    assert decode_rows(rendered, conversation) == rows


def test_projection_validates_raw_cell_types_and_does_not_accept_boolean_row_index():
    with pytest.raises(TypeError):
        project([['q', {'path': 'file', 'name': 'name'}]])
    result = project([['q', 'a']], [], [artifact('f', 'current')], current_turn_id='current', answer_row=False)
    assert result.view_only_rows == {1}


def test_shifted_preview_with_same_answers_does_not_override_known_user_identity():
    items = [item('u1', 'user', 'one?', 't1'), item('a1', 'assistant', 'same', 't1'),
             item('u2', 'user', 'two?', 't2'), item('a2', 'assistant', 'same', 't2')]
    result = project([['two?', 'same'], ['new?', 'same']], items,
                     [artifact('old', 't1'), artifact('visible', 't2')])
    assert result.artifact_anchors['visible'] == result.row_anchors[0]
    assert result.artifact_anchors['old'] == result.row_anchors[2]
    assert result.view_only_rows == {2}


def test_actual_project_converters_remain_idempotent_and_copy_raw_stays_clean():
    # Load the actual pure converter definitions without importing unrelated
    # provider configuration or requiring network access during this test.
    import ast
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'modules' / 'utils.py'
    selected = {'convert_user_before_marked', 'convert_bot_before_marked', 'escape_markdown', 'clip_rawtext'}
    tree = ast.parse(path.read_text())
    definitions = ast.Module(body=[node for node in tree.body
                                  if isinstance(node, ast.FunctionDef) and node.name in selected], type_ignores=[])
    namespace = {'re': re}
    exec(compile(ast.fix_missing_locations(definitions), str(path), 'exec'), namespace)
    user_converter = namespace['convert_user_before_marked']
    bot_converter = namespace['convert_bot_before_marked']
    rows = [['<b>question</b> 👋', 'answer\n\n```html\n<span>raw</span>\n```'], ['', None]]
    projection = project(rows, [], [artifact('file-only', 'new-turn')], current_turn_id='new-turn', answer_row=1)
    rendered = render_projection(projection, user_converter, bot_converter)
    assert decode_rows(rendered, 'conversation') == rows
    # Gradio's project overwrite runs these converters again before output.
    assert user_converter(rendered[0][0]) == rendered[0][0]
    assert bot_converter(rendered[0][1]) == rendered[0][1]
    assert bot_converter(rendered[1][1]) == rendered[1][1]
    raw_copy = rendered[0][1].split('<div class="md-message">')[0]
    assert 'agent-message-anchor' not in raw_copy
    assert 'data-agent-message-raw' not in raw_copy


@pytest.mark.parametrize('preview_answer', [None, '', 'same answer'])
def test_long_history_new_preview_uses_linear_path_before_turn_id_arrives(monkeypatch, preview_answer):
    from modules.agent import message_files as agent_message_files
    count = 4000
    items, rows = [], []
    for i in range(count):
        question = 'question ' + str(i)
        answer = '' if i == count - 1 else 'same answer'
        items.extend([item('u' + str(i), 'user', question, 't' + str(i)),
                      item('a' + str(i), 'assistant', answer, 't' + str(i))])
        rows.append([question, answer])
    rows.append(['brand new question', preview_answer])

    def forbid_dynamic(*args):
        pytest.fail('A definite appended preview must not allocate alignment matrices')
    monkeypatch.setattr(agent_message_files, '_align_rows_dynamic', forbid_dynamic)
    # No current_turn_id or answer_row exists yet on the first streamed frame.
    result = project(rows, items, [artifact('old-file', 't0'), artifact('latest-file', 't3999')])
    assert result.rows == rows
    assert result.artifact_anchors['old-file'] == result.row_anchors[0]
    assert result.artifact_anchors['latest-file'] == result.row_anchors[count - 1]
    assert not result.view_only_rows


def test_long_projected_manifest_history_with_new_preview_uses_linear_path(monkeypatch):
    from modules.agent import message_files as agent_message_files
    count = 2000
    items, rows = [], []
    for i in range(count):
        items.extend([item('u' + str(i), 'user', 'manifest ' + str(i), 't' + str(i)),
                      item('a' + str(i), 'assistant', 'completed', 't' + str(i))])
        rows.append(['display question ' + str(i), 'completed'])
    rows.append(['new question', ''])
    monkeypatch.setattr(agent_message_files, '_align_rows_dynamic',
                        lambda *args: pytest.fail('A disjoint preview should take the linear path'))
    result = project(rows, items, [artifact('file', 't1999')])
    assert result.artifact_anchors['file'] == result.row_anchors[count - 1]
    assert not result.view_only_rows


@pytest.mark.parametrize('cloud_user', ['question', 'manifest'])
def test_repeated_appended_row_still_uses_conservative_alignment(monkeypatch, cloud_user):
    from modules.agent import message_files as agent_message_files
    calls = []
    original = agent_message_files._align_rows_dynamic
    def observe_dynamic(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(agent_message_files, '_align_rows_dynamic', observe_dynamic)
    items = [item('u', 'user', cloud_user, 't'), item('a', 'assistant', 'same', 't')]
    rows = [['question', 'same'], ['question', 'same']]
    result = project(rows, items, [artifact('file', 't')])
    assert calls == [True]
    assert result.view_only_rows == {2}
    assert result.artifact_anchors['file'] == result.row_anchors[2]
    assert result.artifact_anchors['file'] not in (result.row_anchors[0], result.row_anchors[1])


def test_true_repeated_subset_still_preserves_ambiguity_after_fast_path(monkeypatch):
    from modules.agent import message_files as agent_message_files
    calls = []
    original = agent_message_files._align_rows_dynamic
    def observe_dynamic(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(agent_message_files, '_align_rows_dynamic', observe_dynamic)
    items = [item('u1', 'user', 'same question', 't1'), item('a1', 'assistant', 'same answer', 't1'),
             item('u2', 'user', 'same question', 't2'), item('a2', 'assistant', 'same answer', 't2')]
    result = project([['same question', 'same answer']], items,
                     [artifact('one', 't1'), artifact('two', 't2')])
    assert calls == [True]
    assert result.view_only_rows == {1, 2}
    assert result.row_anchors[0] not in result.artifact_anchors.values()


@pytest.mark.parametrize('file_cell', [['/unused/photo.png'], ['/unused/photo.png', None],
                                     ['/unused/photo.png', '图片 👋'], ('/unused/photo.png',),
                                     ('/unused/photo.png', None), ('/unused/photo.png', 'image')])
def test_native_file_cell_formats_pass_through_without_text_conversion(file_cell, monkeypatch):
    import builtins
    rows = [[file_cell, None], ['question', 'answer'], [None, file_cell], [file_cell, 'caption']]
    before = deepcopy(rows)
    calls = []
    def formatter(value):
        assert isinstance(value, str)
        calls.append(value)
        return '<div>' + value + '</div>'
    def no_file_reads(*args, **kwargs):
        pytest.fail('Projection must not open native file-cell paths')
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', no_file_reads)
        result = project(rows)
        rendered = render_projection(result, formatter, formatter)
        decoded = decode_rows(rendered, 'conversation')
    assert decoded == rows == before
    assert calls == ['question', 'answer', 'caption']
    assert set(result.row_anchors) == {1, 3}
    assert rendered[0][0] == file_cell and type(rendered[0][0]) is type(file_cell)
    assert rendered[2][1] == file_cell and type(decoded[2][1]) is type(file_cell)
    assert not result.view_only_rows
    if isinstance(file_cell, list):
        assert result.rows[0][0] is not file_cell
        assert rendered[0][0] is not result.rows[0][0]
        assert decoded[0][0] is not rendered[0][0]


def test_native_files_before_between_and_after_messages_preserve_official_anchors():
    ordinary = [['first?', 'first!'], ['second?', 'second!']]
    files = [[['/unused/before.png', None], None],
             [None, ('/unused/between.pdf', 'PDF')],
             [['/unused/after.png'], None]]
    rows = [files[0], ordinary[0], files[1], ordinary[1], files[2]]
    records = [artifact('first', 't1'), artifact('second', 't2')]
    baseline = project(ordinary, two_turns(), records)
    mixed = project(rows, two_turns(), records)
    assert mixed.artifact_anchors == baseline.artifact_anchors
    assert mixed.artifact_anchors['first'] == mixed.row_anchors[1]
    assert mixed.artifact_anchors['second'] == mixed.row_anchors[3]
    assert set(mixed.row_anchors) == {1, 3}
    assert not mixed.view_only_rows
    assert decode_rows(render(mixed), 'conversation') == rows


def test_native_file_cells_are_not_cloud_text_candidates_even_when_path_text_matches():
    items = [item('u', 'user', '/unused/photo.png', 't'), item('a', 'assistant', 'caption', 't')]
    rows = [[['/unused/photo.png', None], 'caption'], [None, ('/unused/answer.txt',)]]
    result = project(rows, items, [artifact('file', 't')])
    assert result.view_only_rows == {2}
    assert result.artifact_anchors['file'] == result.row_anchors[2]
    assert result.artifact_anchors['file'] != result.row_anchors[0]
    assert 1 not in result.row_anchors
    assert decode_rows(render(result), 'conversation') == rows


def test_current_turn_does_not_replace_assistant_native_file_cell_with_text_marker():
    rows = [['question', ('/unused/answer.pdf', 'Answer')]]
    result = project(rows, [], [artifact('file', 'current')], current_turn_id='current', answer_row=0)
    assert result.view_only_rows == {1}
    assert 0 not in result.row_anchors
    assert render(result)[0][1] == rows[0][1]
    assert decode_rows(render(result), 'conversation') == rows


def test_file_only_placeholder_and_native_files_roundtrip_together():
    rows = [[['/unused/image.png', None], None], ['make a file', None]]
    items = [item('u', 'user', 'make a file', 't')]
    result = project(rows, items, [artifact('known', 't'), artifact('unknown', 'missing')])
    assert result.artifact_anchors['known'] == result.row_anchors[1]
    assert result.view_only_rows == {2}
    assert decode_rows(render(result), 'conversation') == rows
    assert result.rows[0] == rows[0]


@pytest.mark.parametrize('invalid', [{'path': '/unused/image.png'}, {'not': 'file'}, [], [3],
                                    ['/unused/image.png', 3], ['/unused/image.png', None, 'extra'],
                                    [None, 'alt'], [['nested path'], None], object()])
def test_projection_still_rejects_dicts_and_invalid_native_file_shapes(invalid):
    with pytest.raises(TypeError):
        project([[invalid, None]])
    with pytest.raises(TypeError):
        project([[None, invalid]])


def test_real_ordinary_image_history_switch_preserves_native_file_view(tmp_path, monkeypatch):
    # Reproduce the independent review's first compatibility test through the
    # real ordinary save/load and model-switch branches, with offline providers.
    from pathlib import Path
    from offline_models import install
    from agent_fixtures import select
    from modules.agent.ui import AgentPanel
    environment = install(Path(__file__).resolve().parents[2], tmp_path / 'history')
    environment.agents.shared.chuanhu_path = str(tmp_path)
    monkeypatch.setattr(environment.agents, 'worker_messages',
                        lambda command: (_ for _ in ()).throw(AssertionError('Unmocked worker')))
    image = tmp_path / 'photo.png'
    image.write_bytes(b'synthetic local image bytes')
    ordinary = select(environment, name='GPT3.5 Turbo')
    ordinary.history = [
        {'role': 'image', 'content': str(image)},
        {'role': 'user', 'content': 'Describe this image'},
        {'role': 'assistant', 'content': 'An ordinary image answer'},
    ]
    ordinary.auto_save([])
    ordinary.load_chat_history(ordinary.history_file_path)
    assert ordinary.chatbot == [[[str(image), None], None],
                                ['Describe this image', 'An ordinary image answer']]
    original = deepcopy(ordinary.chatbot)
    agent = select(environment, ordinary)
    assert agent.is_hosted_agent and agent.chatbot == original
    rendered = AgentPanel().render_chat(agent, agent.chatbot)
    assert rendered[0] == original[0]
    assert decode_rows(rendered, agent._conversation_id) == original
