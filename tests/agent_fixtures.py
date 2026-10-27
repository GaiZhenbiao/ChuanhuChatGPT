"""共享的离线模型夹具；使用合成工作器与独立历史目录。"""
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import json
import tempfile
import threading
import pytest
import gradio as gr
from offline_models import install

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def env(tmp_path, monkeypatch):
    env = install(ROOT, tmp_path/'history')
    env.agents.shared.chuanhu_path = str(tmp_path)
    monkeypatch.setattr(env.agents, 'worker_messages', lambda command: (_ for _ in ()).throw(AssertionError('Unmocked worker')))
    yield env
    # Async file work must finish before monkeypatch restores worker/stdio hooks.
    settle_files(timeout=8)

def request(name='browser-one', username=None):
    return SimpleNamespace(username=username, session_hash=name)

def select(env, original=None, browser='browser-one', name='OpenAI Agent', username=None):
    return env.factory.change_model(name,None,'ordinary-key',None,None,'ordinary prompt',username or '',original,request(browser,username))[0]

def complete(env, monkeypatch, artifacts=False):
    calls=[]
    folder=Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))
    file=folder/'synthetic.txt'; file.write_text('Synthetic Agent artifact')
    def worker(command):
        calls.append(deepcopy(command))
        if command['action']=='run':
            yield dict(type='progress',session_id=command.get('session_id') or 'sess_test',turn_id='turn_'+str(len(calls)),outcome='in_progress')
            yield dict(type='result',session_id=command.get('session_id') or 'sess_test',outcome='completed',text='Agent synthetic answer')
        elif command['action']=='download':
            yield dict(type='result',artifacts=[dict(id='art_one',session_id='sess_test',turn_id='turn_1',name=file.name,path=str(file),status='ready',size=file.stat().st_size,type='text/plain')] if artifacts else [])
        elif command['action'] in ('inspect','recover','recover_unknown'):
            yield dict(type='result',session_id='sess_test',outcome='completed',text='Recovered answer')
        elif command['action']=='update':
            yield dict(type='result',settings={key:command[key] for key in ('model','reasoning')})
        else: raise AssertionError(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    return calls,file

def settle_files(model=None, timeout=8):
    import time
    from modules.agent.file_jobs import FILE_JOBS
    until=time.monotonic()+timeout
    while FILE_JOBS.queue.unfinished_tasks and time.monotonic()<until:
        time.sleep(.01)
    assert not FILE_JOBS.queue.unfinished_tasks, 'Offline file job did not settle'
    if model is not None and getattr(model, 'is_hosted_agent', False): model.refresh_files(resume=False)


def send(env, model, text='hello', chatbot=None, browser='browser-one', username=None):
    frames = list(env.wrappers['predict'](model,text,model.chatbot if chatbot is None else chatbot,request=request(browser,username)))
    # Existing completed-file assertions inspect file readiness, independent of
    # the already completed main queue. Latency tests use the iterator directly.
    settle_files(model)
    return frames
