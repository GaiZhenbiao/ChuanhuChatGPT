"""Cross-feature deletion, inheritance and rejected-request lifecycle offline."""
from copy import deepcopy
from threading import Event
import pytest
from agent_fixtures import env,request,select,send
from test_background_tasks import new_chat,finish,open_history
from test_history_deletion import saved,deleted


@pytest.mark.parametrize('name,legacy,expected',[
    ('gpt-6.1-sol','minimal','low'),
    ('gpt-6-astra','minimal','low'),
    ('gpt-6-sol','none','none'),
    ('gpt-6.1-sol',None,None),
    ('custom-agent','minimal','minimal'),
])
def test_restored_history_delete_new_chat_keeps_compatible_choice_and_first_send(env,monkeypatch,name,legacy,expected):
    old=saved(env)
    old.model_name=name;old._reasoning=legacy
    old._session_settings=dict(model=name,reasoning=legacy,instructions=old.system_prompt,tools=deepcopy(old._tool_settings))
    old.auto_save(old.chatbot)
    restored=open_history(env,monkeypatch,old.new_view(),old.history_file_path)
    assert restored._needs_sync and restored.agent_model_choice==(name,expected)
    env.wrappers['delete_chat_history'](restored,restored.history_file_path,request=request())
    fresh=new_chat(env,restored)
    assert fresh.agent_model_choice==(name,expected) and fresh._last_request_error=={}
    commands=[]
    def worker(command):
        commands.append(command)
        if command['action']=='run':yield dict(type='result',session_id='fresh-session',turn_id='fresh-turn',outcome='completed',text='fresh answer')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    send(env,fresh,'fresh request')
    run=next(c for c in commands if c['action']=='run')
    assert run['model']==name and run['reasoning']==expected
    assert fresh.chatbot==[['fresh request','fresh answer']] and not fresh._running
    deleted(env,old)


def test_late_400_after_deleted_task_does_not_restore_binding_or_pollute_new_view(env,monkeypatch):
    ready,release=Event(),Event();calls=[]
    def worker(command):
        calls.append(command['action'])
        if command['action']=='run' and command['prompt']=='old request':
            yield dict(type='progress',session_id='old-session',turn_id='old-turn',outcome='in_progress',submission_started=True)
            ready.set();assert release.wait(5)
            assert command['_observe_cancel']()
            yield dict(type='error',outcome='incomplete',message='Synthetic request rejected (HTTP 400)',diagnostics=dict(status_code=400,code='invalid_request_error',param='agent.reasoning.effort',phase='run.session_create'))
        elif command['action']=='run':
            assert command['reasoning']=='low'
            yield dict(type='result',session_id='fresh-session',turn_id='fresh-turn',outcome='completed',text='new answer')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    old=select(env);old._reasoning='minimal'
    stream=env.wrappers['predict'](old,'old request',[],request=request());next(stream)
    assert ready.wait(3);task=old._background_task
    try:
        env.wrappers['delete_chat_history'](old,old.history_file_path,request=request())
        fresh=new_chat(env,old);assert fresh._reasoning=='low'
        send(env,fresh,'new request');assert fresh.chatbot==[['new request','new answer']]
        release.set();finish(task);deleted(env,old)
        assert fresh._last_request_error=={} and fresh._state['outcome']=='completed'
        assert 'cancel' not in calls
    finally:release.set();task.thread.join(5);stream.close()
