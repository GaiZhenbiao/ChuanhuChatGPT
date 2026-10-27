import logging
import pytest
from agent_fixtures import settle_files, env, select, send
from test_runtime import message


@pytest.mark.parametrize('path', ['predict', 'reconnect', 'observe'])
def test_final_answer_logging_waits_for_reconciliation_and_deduplicates(env, monkeypatch, caplog, path):
    model = select(env)
    final = '完整正文\n' + 'long answer ' * 2000
    partial = 'partial'
    def worker(command):
        if command['action'] == 'download':
            yield dict(type='result', artifacts=[])
            return
        assert command['action'] in ('run', 'recover', 'observe')
        yield dict(type='progress', session_id='sess_test', turn_id='t1', outcome='completed', text=partial)
        assert not [r for r in caplog.records if r.msg == '回答为：%s']
        yield dict(type='result', session_id='sess_test', turn_id='t1', outcome='completed',
                   sync_complete=True, items=[message('u1', 'question', role='user'), message('a1', final)])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    caplog.set_level(logging.INFO)
    if path == 'predict':
        send(env, model, 'question')
    else:
        model._state = dict(generation='g', session_id='sess_test', turn_id='t1', outcome='incomplete')
        model.history = [{'role': 'user', 'content': 'question'}, {'role': 'assistant', 'content': partial}]
        model._display = model.chatbot = [['question', partial]]
        model._answer_index, model._answer_row = 1, 0
        model._needs_sync = True
        model._session_settings = model._current_settings()
        list(model.reconnect() if path == 'reconnect' else model.observe_history())
    records = [r for r in caplog.records if r.msg == '回答为：%s']
    assert len(records) == 1 and records[0].getMessage() == '回答为：' + final
    # Browsing final snapshots stays quiet, including a later historical extension.
    snapshot = dict(type='result', session_id='sess_test', turn_id='t1', outcome='completed',
                    sync_complete=True, items=[message('u1', 'question', role='user'), message('a1', final)])
    model._accept(snapshot, model._state['generation'], restoring=True)
    assert len([r for r in caplog.records if r.msg == '回答为：%s']) == 1
    snapshot['items'][-1] = message('a1', final + '\nlate completion')
    model._accept(snapshot, model._state['generation'], restoring=True)
    records = [r for r in caplog.records if r.msg == '回答为：%s']
    assert len(records) == 1
    assert model.history[-1]['content'] == final + '\nlate completion'


@pytest.mark.parametrize('outcome', ['failed', 'cancelled'])
@pytest.mark.parametrize('path', ['predict', 'reconnect', 'observe'])
def test_empty_terminal_turn_never_logs_previous_answer(env, monkeypatch, caplog, outcome, path):
    model = select(env)
    model.history = [{'role': 'user', 'content': 'previous question'}, {'role': 'assistant', 'content': 'previous answer'}]
    model._display = model.chatbot = [['previous question', 'previous answer']]
    previous_items = [message('old-u', 'previous question', 'old', role='user'), message('old-a', 'previous answer', 'old')]
    def worker(command):
        if command['action'] == 'download':
            yield dict(type='result', artifacts=[])
        else:
            yield dict(type='result', session_id='sess_test', turn_id='new', outcome=outcome,
                       sync_complete=True, items=previous_items + [message('new-u', 'new question', 'new', role='user')])
    monkeypatch.setattr(env.agents, 'worker_messages', worker)
    caplog.set_level(logging.INFO)
    if path == 'predict':
        send(env, model, 'new question')
    else:
        model._state = dict(generation='g', session_id='sess_test', turn_id='new', outcome='incomplete')
        model._needs_sync = True
        model._session_settings = model._current_settings()
        list(model.reconnect() if path == 'reconnect' else model.observe_history())
    assert not [r for r in caplog.records if r.msg == '回答为：%s']


def test_completed_history_restoration_is_quiet_across_new_views(env, caplog):
    from copy import deepcopy
    model = select(env)
    snapshot = dict(type='result', session_id='sess_test', turn_id='t1', outcome='completed',
                    sync_complete=True, items=[message('u1', 'question', role='user'), message('a1', 'answer')])
    model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    caplog.set_level(logging.INFO)
    model._accept(snapshot,'g')
    assert len([r for r in caplog.records if r.msg=='回答为：%s'])==1
    for view in [model.new_view(),model.new_view(),model.new_view()]:
        view._state=deepcopy(model._state)
        view._accept(snapshot,'g',restoring=True)
    assert len([r for r in caplog.records if r.msg=='回答为：%s'])==1


@pytest.mark.parametrize('path', ['observe', 'reconnect'])
def test_completed_view_restoration_does_not_replay_tools_or_files(env, monkeypatch, caplog, path):
    from copy import deepcopy
    from test_tool_logging import items, records
    model=select(env)
    snapshot=dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,
                  items=items()+[message('u1','question',role='user'),message('a1','answer')])
    artifact=dict(id='f',session_id='sess_test',turn_id='t1',name='old.txt',status='failed',error='offline cache')
    model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='completed')
    model._accept(snapshot,'g',restoring=True)
    def worker(command):
        yield deepcopy(dict(type='result',artifacts=[artifact]) if command['action']=='download' else snapshot)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    caplog.set_level(logging.INFO)
    for view in [model.new_view(), model.new_view(), model.new_view()]:
        view._state=deepcopy(model._state)
        view._needs_sync=True
        view._session_settings=view._current_settings()
        list(view.observe_history() if path=='observe' else view.reconnect())
        settle_files(view)
        assert view.history[-1]['content']=='answer'
        assert view._artifacts[0]['name']=='old.txt'
    assert not records(caplog)
    assert not [r for r in caplog.records if r.msg=='回答为：%s']


def test_nullable_final_then_normal_turn_logs_once_each_and_restore_stays_quiet(env,caplog):
    from copy import deepcopy
    model=select(env);caplog.set_level(logging.INFO)
    first=dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,
               items=[message('u1','question',role='user'),message(None,'nullable complete')],
               item_occurrences={1:'answer-receipt'},capture={'items':'complete'})
    model._state.update(generation='g1',session_id='sess_test',turn_id='t1',outcome='in_progress')
    model._accept(first,'g1')
    model._state.update(generation='g2',turn_id=None,outcome='in_progress')
    second=dict(first,turn_id='t2',items=first['items']+[message('u2','next','t2',role='user'),message('a2','normal complete','t2')])
    model._accept(second,'g2')
    records=[r.getMessage() for r in caplog.records if r.msg=='回答为：%s']
    assert records==['回答为：nullable complete','回答为：normal complete']
    view=model.new_view();view.history_file_path=model.history_file_path;view._restore_binding()
    view._accept(deepcopy(second),'g2',restoring=True)
    assert [r.getMessage() for r in caplog.records if r.msg=='回答为：%s']==records
