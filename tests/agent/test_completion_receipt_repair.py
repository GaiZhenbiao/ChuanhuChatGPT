"""A superseding full receipt repairs only known coverage, never stream integrity."""
from copy import deepcopy
import pytest
from modules.agent import runtime
from test_runtime import FakeClient
from test_terminal_integrity import accepted, started, terminal, final, item, reasoning, event


@pytest.mark.parametrize('summary', [False, True])
@pytest.mark.parametrize('partial_kind', ['item.added', 'item.updated', 'item.done'])
def test_full_done_supersedes_partial_receipt_without_get(summary, partial_kind):
    value = reasoning(['first']) if summary else item(text='first')
    fields = dict(item_id=value['id'], output_index=0)
    fields['summary_index' if summary else 'content_index'] = 1
    fields['text'] = 'second'
    full = deepcopy(value)
    full['summary' if summary else 'content'].append(dict(type='summary_text' if summary else 'output_text', text='rewritten second'))
    events = [started(), event('item.added', event_id='initial', output_index=0, item=dict(value, status='in_progress')),
              event('reasoning_summary_text.done' if summary else 'output_text.done', **fields),
              event(partial_kind, event_id='partial', output_index=0, item=value),
              dict(final(full), event_id='full'), terminal()]
    client = FakeClient(events)
    state = runtime.run_task(client, 'synthetic', 'model')
    assert state.turn_complete and state.sync_complete is None
    assert 'retrieve' not in client.trace
    assert state.items[value['id']] == dict(full, output_index=0)


@pytest.mark.parametrize('conflict', ['gap', 'identity', 'position', 'unknown', 'type', 'part_kind', 'malformed'])
def test_full_done_does_not_erase_independent_integrity_failure(conflict):
    state = accepted(started())
    state.accept(event('output_text.done', item_id='answer', output_index=0, content_index=1, text='second'))
    state.accept(dict(final(item()), event_id='partial'))
    if conflict == 'gap': state.stream_gap = True
    elif conflict == 'identity': state.accept(dict(started(agent_id='other'), event_id='conflict'))
    elif conflict == 'position': state.accept(event('output_text.done', event_id='conflict', item_id='answer', output_index=1, content_index=0, text='first'))
    elif conflict == 'unknown': state.accept(event('future', event_id='conflict'))
    else:
        invalid = item()
        if conflict == 'type': invalid['type'] = 'agent_message'
        if conflict == 'part_kind': invalid['content'][0]['type'] = 'text'
        if conflict == 'malformed': invalid['content'] = None
        state.accept(event('item.updated', event_id='conflict', output_index=0, item=invalid))
    full = item(); full['content'].append(dict(type='output_text', text='second'))
    state.accept(dict(final(full), event_id='full')); state.accept(terminal())
    assert not state.turn_complete
    client = FakeClient(saved_turn='completed'); client.saved_items = [full]
    runtime._reconcile_terminal(client, state)
    assert 'retrieve' in client.trace


def test_new_part_after_final_can_be_repaired_by_full_authoritative_done():
    state = accepted(started(), final(item()))
    state.accept(event('output_text.done', item_id='answer', output_index=0, content_index=1, text='second'))
    full = item(); full['content'].append(dict(type='output_text', text='second'))
    state.accept(dict(final(full), event_id='replacement')); state.accept(terminal())
    assert state.turn_complete


def test_timing_rejects_sensitive_and_unbounded_fields(caplog):
    import logging
    from modules.agent.completion_timing import new_timing, safe_timing, mark, report, _reports
    timing = new_timing()
    timing.update(api_key='SECRET', prompt='PRIVATE', filename='PRIVATE.txt', session_id='sess_secret')
    timing['gate_reasons'] = ['missing_output', 'SECRET', {}, 'missing_output']
    timing['stages'] = {'root_terminal': 123.0, 'SECRET': 4, 'result_received': float('nan'), 'task_unlocked': 10 ** 1000}
    safe = safe_timing(timing)
    assert safe['gate_reasons'] == ['missing_output']
    assert safe['stages'] == {'root_terminal': 123.0}
    mark(safe, 'gate_checked')
    with caplog.at_level(logging.INFO, logger='modules.agent.completion_timing'):
        report(timing)
        _reports.join()
    assert 'SECRET' not in caplog.text and 'PRIVATE' not in caplog.text and 'sess_secret' not in caplog.text
    assert 'agent_completion_timing' in caplog.text
    assert safe_timing(dict(timing, trace='SECRET')) is None


def test_diagnostic_queue_never_waits_for_logger(monkeypatch):
    from threading import Event
    from modules.agent import completion_timing as timing
    entered, release = Event(), Event()
    timing._reports.join()
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
    monkeypatch.setattr(timing.logging.getLogger(timing.__name__), 'info', blocked)
    try:
        timing.report(timing.new_timing())
        assert entered.wait(2)
        for _ in range(100): timing.report(timing.new_timing())
        assert timing._reports.qsize() == 64
    finally:
        release.set()
        timing._reports.join()


def test_old_ui_subscriber_reports_its_own_timing(monkeypatch):
    from threading import Condition, RLock
    from types import SimpleNamespace
    from modules.agent import tasks
    from modules.agent.completion_timing import new_timing
    task = tasks.BackgroundTask.__new__(tasks.BackgroundTask)
    task.deleted = False; task.done = True; task.error = None
    task.condition = Condition(); task.revision = 1
    task.owner = 'synthetic'; task.conversation = 'synthetic'
    task.completion_timing = new_timing()
    newer = new_timing()
    task.model = SimpleNamespace(_completion_timing=newer)
    task.snapshot = ({'_display': []}, 'done')
    view = SimpleNamespace(_retired=False, agent_choice_target='same', _lock=RLock(),
        _owner=task.owner, _conversation_id=task.conversation, _background_task=task,
        refresh_files=lambda **kwargs: None)
    reports = []
    monkeypatch.setattr(tasks, 'report_completion', reports.append)
    assert list(task.subscribe(view)) == [([], 'done')]
    assert reports[0]['trace'] == task.completion_timing['trace'] != newer['trace']
    assert 'ui_final_frame' in reports[0]['stages']
    assert newer['stages'] == {} and task.completion_timing['stages'] == {}


@pytest.mark.parametrize('action', ['run', 'recover', 'observe'])
@pytest.mark.parametrize('complete', [False, True])
def test_worker_final_result_once_and_cleanup_cannot_revoke_it(monkeypatch, action, complete):
    from contextlib import nullcontext
    from io import StringIO
    import json
    from types import SimpleNamespace
    from modules.agent import worker, artifacts
    from test_finalization_boundary import complete_state
    state = complete_state()
    # Recovery must require GET authority even if the stream is fully sealed.
    state.sync_complete = complete if action != 'run' else None
    if action == 'run' and not complete: state.final_items.clear()
    observer = SimpleNamespace(snapshot=lambda *args: [], observe_session=lambda *args: None)
    monkeypatch.setattr(artifacts, 'ArtifactObserver', lambda *args, **kwargs: nullcontext(observer))
    monkeypatch.setattr(worker, 'create_client', lambda *args: nullcontext(FakeClient()))
    monkeypatch.setattr(worker.sys, 'stdin', StringIO(json.dumps(dict(action=action, session_id='sess_one', prompt='synthetic', model='model'))))
    def operation(*args, on_progress, **kwargs):
        on_progress(state); on_progress(state)
        raise RuntimeError('synthetic teardown failure')
    monkeypatch.setattr(worker, 'run_task', operation)
    monkeypatch.setattr(worker, 'recover_stream', operation)
    messages = []
    monkeypatch.setattr(worker, 'emit', lambda kind, **data: messages.append(dict(type=kind, **data)))
    worker.main()
    kinds = [message['type'] for message in messages]
    assert kinds == (['result'] if complete else ['progress', 'progress', 'error'])
