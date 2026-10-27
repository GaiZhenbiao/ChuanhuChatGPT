from threading import Event
import logging
import pytest
from agent_fixtures import env,select
from test_runtime import message
from test_history_visual_state import controls
from test_ui import panel_app

@pytest.mark.parametrize('path',['observe','reconnect'])
def test_unreconciled_terminal_first_final_answer_still_logged(env,monkeypatch,caplog,path):
    model=select(env)
    model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='completed')
    model._needs_sync=True
    model._display=model.chatbot=[['question','partial']]
    model.history=[{'role':'user','content':'question'},{'role':'assistant','content':'partial'}]
    model._answer_index=1;model._answer_row=0
    model._session_settings=model._current_settings()
    def worker(command):
        if command['action']=='download':yield dict(type='result',artifacts=[])
        else:yield dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,items=[message('u1','question',role='user'),message('a1','first authoritative final')])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    caplog.set_level(logging.INFO)
    list(model.observe_history() if path=='observe' else model.reconnect())
    assert any(r.msg=='回答为：%s' and 'first authoritative final' in r.getMessage() for r in caplog.records)

def test_readonly_slot_still_blocks_visible_send_after_sync(env):
    from modules.agent.tasks import TaskRegistry
    model=select(env);model._state.update(generation='g',session_id='s',turn_id='t',outcome='completed');model._needs_sync=False
    app,panel,state=panel_app(model);legacy,caps=controls(app,panel)
    ready,release=Event(),Event()
    def observe():ready.set();release.wait(3);yield model.chatbot,''
    task=TaskRegistry().start(model,observe,read_only=True)
    try:
        assert ready.wait(2)
        with pytest.raises(Exception):model._assert_idle()
        assert caps.stream_values(model)[caps.stream_outputs.index(caps.submit)]['interactive'] is False
    finally:release.set();task.thread.join(4);app.close()


@pytest.mark.parametrize('path',['observe','reconnect'])
def test_terminal_progress_receipt_survives_binding_and_only_final_reconciliation_logs(env,monkeypatch,caplog,path):
    from copy import deepcopy
    from test_tool_logging import items, records
    model=select(env)
    model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    model._display=model.chatbot=[['question','partial']]
    model.history=[{'role':'user','content':'question'},{'role':'assistant','content':'partial'}]
    model._answer_index=1;model._answer_row=0
    model._session_settings=model._current_settings()
    model._accept(dict(type='progress',session_id='sess_test',turn_id='t1',outcome='completed',text='partial'),'g')
    assert 'log_reconciled' not in model._store().get(model._owner,model.history_file_path)['state']
    final=dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,
               items=items()+[message('u1','question',role='user'),message('a1','first authoritative final')])
    def worker(command):
        yield deepcopy(dict(type='result',artifacts=[]) if command['action']=='download' else final)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    caplog.set_level(logging.INFO)
    restored=model.new_view();restored.history_file_path=model.history_file_path;restored.history=deepcopy(model.history);restored._display=restored.chatbot=deepcopy(model.chatbot)
    restored._restore_binding()
    list(restored.observe_history() if path=='observe' else restored.reconnect())
    assert len([r for r in caplog.records if r.msg=='回答为：%s'])==1
    first=records(caplog);assert any('代码/文件执行' in line for line in first)
    binding=restored._store().get(restored._owner,restored.history_file_path)
    assert binding['state']['log_reconciled']=={'session_id':'sess_test','turn_id':'t1'}
    again=restored.new_view();again.history_file_path=restored.history_file_path;again.history=deepcopy(restored.history);again._display=again.chatbot=deepcopy(restored.chatbot)
    again._restore_binding()
    list(again.observe_history() if path=='observe' else again.reconnect())
    assert len([r for r in caplog.records if r.msg=='回答为：%s'])==1 and records(caplog)==first
