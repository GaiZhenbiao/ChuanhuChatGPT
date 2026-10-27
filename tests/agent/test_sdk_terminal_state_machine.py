"""Actual SDK/IPC/model controls for complete, cancelled and uncertain reads."""
import json
from pathlib import Path
import subprocess,sys,time
import gradio as gr
import pytest
from agent_fixtures import env,select,request
from test_finalization_boundary import wait_main,wait_files
from modules.agent import transport

@pytest.mark.parametrize('case',['healthy','normal_multi','normal_reasoning','cancelled_incomplete','failed_incomplete','get_pending_reconnect'])
def test_sdk_typed_completion_and_reconnect(env,monkeypatch,tmp_path,case):
    trace=tmp_path/'trace.jsonl';real=subprocess.Popen;children=[]
    def spawn(args,**kwargs):
        child=real([sys.executable,str(Path(__file__).with_name('offline_finalization_worker.py')),str(env.root),case,str(trace),str(tmp_path)],**kwargs)
        children.append(child);return child
    monkeypatch.setattr(transport.subprocess,'Popen',spawn)
    monkeypatch.setattr(env.agents,'worker_messages',transport.worker_messages)
    model=select(env);stream=env.wrappers['predict'](model,'Synthetic prompt',[],request=request());next(stream)
    try:
        wait_main(model);ended=time.monotonic();wait_files(model)
        events=[json.loads(line) for line in trace.read_text().splitlines()]
        if case=='get_pending_reconnect':
            assert model._needs_sync
            with pytest.raises(gr.Error):model._assert_idle()
            assert 'Second canonical part' in str(model.history)
            (tmp_path/'ready-get').write_text('ready')
            list(model.reconnect());wait_files(model)
            assert not model._needs_sync
            model._assert_idle()
            assert 'Second canonical part' in str(model.history)
        else:
            model._assert_idle()
            assert not model._needs_sync and not any(e['event'].startswith('GET_') for e in events)
            assert not any(e['event']=='EOF_requested' for e in events)
            assert ended-next(e['time'] for e in events if e['event']=='terminal')<1.0
            assert model._transcript['capture']['items']=='partial'
            if case=='normal_multi':assert 'Second canonical part' in str(model.history)
            if case=='normal_reasoning':assert 'Public summary' in json.dumps(model._transcript)
            if case.endswith('_incomplete'):
                expected=case.split('_')[0]
                assert model._state['outcome']==expected
                binding=model._store().get(model._owner,model.history_file_path)
                assert binding['state']['outcome']==expected and binding['local_phase']=='settled'
    finally:
        stream.close()
        for child in children:
            if child.poll() is None:child.terminate()
