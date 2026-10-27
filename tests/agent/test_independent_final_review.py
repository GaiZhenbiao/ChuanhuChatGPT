from copy import deepcopy
import json, logging
import pytest
import gradio as gr
from agent_fixtures import env, select
from test_runtime import message
from modules.agent import transcript


def test_nullable_final_message_is_logged_complete(env,caplog):
    model=select(env)
    model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    payload=dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,
        items=[message('u','question',role='user'),message(None,'complete nullable final')],
        item_occurrences={1:'stable-answer-receipt'},capture={'items':'complete'})
    caplog.set_level(logging.INFO)
    model._accept(payload,'g')
    assert model.history[-1]['content']=='complete nullable final'
    records=[r for r in caplog.records if r.msg=='回答为：%s']
    assert len(records)==1 and records[0].getMessage()=='回答为：complete nullable final'


def test_nullable_record_recovery_repeated_full_read(env):
    model=select(env)
    model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    payload=dict(type='result',session_id='sess_test',turn_id='t1',outcome='completed',sync_complete=True,
        items=[message('u','question',role='user'),message(None,'complete nullable final')],capture={'items':'complete'})
    model._accept(payload,'g',restoring=True)
    original=deepcopy(model._transcript)
    with pytest.raises(gr.Error,match='已有记录已保留'):
        model._accept(payload,'g',restoring=True)
    assert model._transcript==original


def test_malformed_future_import_is_inert_and_does_not_write(env):
    model=select(env);before=list(env.history_dir.glob('*.json'))
    for value in ({'history_format':{'name':'chuanhu','version':999},'history':[]},
                  {'history_format':{'name':'chuanhu','version':2},'agent_transcript':{'version':999}},
                  {'history_format':{'name':'chuanhu','version':2},'agent_transcript':{'version':1}},
                  {'history':[{'role':'assistant','content':None}]}):
        with pytest.raises(gr.Error):model.upload_chat_history(json.dumps(value).encode())
        assert list(env.history_dir.glob('*.json'))==before
        assert not model._state.get('session_id')
