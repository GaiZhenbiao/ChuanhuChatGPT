"""SDK/worker/IPC and private SQLite history-load recovery, with all HTTP mocked."""
from pathlib import Path
import json,subprocess,sys
import gradio as gr
import pytest
from agent_fixtures import env,select,request
from test_finalization_boundary import wait_main,wait_files
from modules.agent import transport

@pytest.mark.parametrize('storage',['receipt','legacy'])
@pytest.mark.parametrize('read',['truncated','wrong_agent','full','rewritten'])
def test_durable_observations_survive_history_load_and_repeated_real_worker_get(env,monkeypatch,tmp_path,storage,read):
    case='receipt_'+read;trace=tmp_path/'trace.jsonl';popen=subprocess.Popen;children=[]
    def spawn(args,**kwargs):
        child=popen([sys.executable,str(Path(__file__).with_name('offline_finalization_worker.py')),str(env.root),case,str(trace),str(tmp_path)],**kwargs)
        children.append(child);return child
    monkeypatch.setattr(transport.subprocess,'Popen',spawn);monkeypatch.setattr(env.agents,'worker_messages',transport.worker_messages)
    model=select(env);stream=env.wrappers['predict'](model,'Synthetic prompt',[],request=request());next(stream)
    try:
        wait_main(model);wait_files(model);stream.close()
        assert model._needs_sync and 'Second canonical part' in str(model.history)
        binding=model._store().get(model._owner,model.history_file_path)
        assert binding['state']['observation']['turns'][0]['root_identity'][2]=='agent_complete'
        if storage=='legacy':
            binding['state'].pop('observation');model._store().put(model._owner,model.history_file_path,binding)
        filename=model.history_file_path
        restored=select(env);restored.load_chat_history(filename)
        assert restored is not model
        (tmp_path/'ready-get').write_text('ready')
        for repetition in range(2):
            list(restored.reconnect());wait_files(restored)
            saved=json.loads((env.history_dir/filename).read_text())
            answers=[row['content'] for row in saved['history'] if row['role']=='assistant']
            assert len(answers)==1
            if read in ('truncated','wrong_agent'):
                assert restored._needs_sync and 'Second canonical part' in str(answers)
                with pytest.raises(gr.Error):restored._assert_idle()
            else:
                restored._assert_idle();assert not restored._needs_sync
                expected='Canonical rewrite second' if read=='rewritten' else 'Second canonical part'
                assert expected in str(answers)
        (tmp_path/'repaired-get').write_text('ready')
        list(restored.reconnect());wait_files(restored)
        restored._assert_idle();assert not restored._needs_sync
        assert 'Canonical rewrite second' in str(restored.history)
        wire=(env.history_dir/filename).read_text()
        assert 'observation' not in json.loads(wire)
        assert model._store().get(model._owner,filename)['state']['observation']['turns'][0]['root_identity'][2]=='agent_complete'
    finally:
        stream.close()
        for child in children:
            if child.poll() is None:child.terminate()
