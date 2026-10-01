"""Real Gradio 4.29 + gradio_client smoke; all Agent traffic is synthetic.

Run: .venv/bin/python tests/ui_smoke.py
Use --serve to inspect the synthetic UI manually. Never reads .env.agents.
"""
import argparse
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
import tempfile
import time
import uuid
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('ALL_PROXY','all_proxy','HTTP_PROXY','http_proxy','HTTPS_PROXY','https_proxy'):
    os.environ.pop(name,None)
os.environ['GRADIO_ANALYTICS_ENABLED']='False'
os.environ['MPLCONFIGDIR']='/tmp/chuanhu-test-matplotlib'
import gradio as gr
from gradio_client import Client
shared=ModuleType('modules.shared');shared.chuanhu_path=str(ROOT);sys.modules['modules.shared']=shared
presets=ModuleType('modules.presets');presets.i18n=lambda text:text;sys.modules['modules.presets']=presets
from modules import extensions, plugin_callbacks
from modules.plugin_context import AppContext


def build():
    temporary=Path(tempfile.mkdtemp(prefix='chuanhu-ui-smoke-'))
    extensions.STATE_FILE=temporary/'state.json'
    extensions.STATE_FILE.write_text('{"version":1,"enabled":{"openai_agents":true}}')
    loaded=extensions.load_extensions(force=True)
    assert not any(item.error for item in loaded)
    extension=next(item for item in loaded if item.id=='openai_agents')
    agents=sys.modules[extension.module_names[-1]]
    # Locate the entry module explicitly; helper module ordering is not an API.
    agents=next(sys.modules[name] for name in extension.module_names if name.endswith('.scripts.main'))
    agents.JOURNAL_DIR=temporary/'journals'
    from fake_agent import FakeAgentBackend
    backend=FakeAgentBackend(temporary)
    agents.worker_messages=backend.messages
    commands=backend.commands
    with gr.Blocks(analytics_enabled=False,title='Chuanhu plugin smoke — synthetic Agent') as demo:
        gr.Markdown('# 插件界面离线验收\n所有 Agent 事件均为模拟，无 API 调用。')
        chatbot=gr.Chatbot(value=[['Offline question','Offline answer']])
        model=gr.State(SimpleNamespace())
        text=gr.Textbox(value='  hello  ')
        with gr.Tabs(): extensions.render_extension_tabs()
        with gr.Tabs(): extensions.render_extension_settings()
        extensions.render_extension_manager()
        plugin_callbacks.invoke('app_ready',AppContext(chatbot,model,text))
    return demo,commands,agents


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');args=parser.parse_args()
    demo,commands,agents=build()
    demo.queue().launch(server_name='127.0.0.1',server_port=8773,share=False,prevent_thread_lock=True,
                        blocked_paths=[str(ROOT/'.env.agents'),str(ROOT/'config.json'),str(ROOT/'plugin_data')],quiet=True)
    if args.serve:
        print('Synthetic UI: http://127.0.0.1:8773',flush=True)
        try:
            while True: time.sleep(1)
        finally: demo.close()
        return
    try:
        client=Client('http://127.0.0.1:8773',verbose=False)
        first=client.predict('first task','model',False,True,[],api_name='/agent_submit')
        assert first[0][-1][1]=='Synthetic result: first task'
        sid=agents.owner_slot(SimpleNamespace(session_hash=client.session_hash,username=None)).state['session_id']
        second=client.predict('follow up','unused',True,True,first[0],api_name='/agent_submit')
        assert second[0][-1][1]=='Synthetic result: follow up'
        assert [c for c in commands if c['action']=='run'][-1]['session_id']==sid
        other=Client('http://127.0.0.1:8773',verbose=False)
        other_result=other.predict('other user','model',False,True,[],api_name='/agent_submit')
        assert other_result[0][-1][1]=='Synthetic result: other user'
        other_sid=agents.owner_slot(SimpleNamespace(session_hash=other.session_hash,username=None)).state['session_id']
        assert sid!=other_sid
        downloaded=client.predict(second[0],api_name='/agent_download')
        assert Path(downloaded[2][0]).read_text().startswith('Synthetic artifact')
        recovered=client.predict(second[0],api_name='/agent_recover')
        assert 'completed' in recovered[1]
        cleaned=client.predict(second[0],True,api_name='/agent_cleanup')
        assert cleaned[0]==[]
        # Real queue double-click regression: only one worker action is sent.
        fresh=Client('http://127.0.0.1:8773',verbose=False)
        before=len([c for c in commands if c['action']=='run'])
        job=fresh.submit('double','model',False,True,[],api_name='/agent_submit')
        duplicate=fresh.submit('double','model',False,True,[],api_name='/agent_submit')
        errors=0
        for pending in (job,duplicate):
            try: pending.result()
            except Exception as error:
                assert '避免重复发送' in str(error)
                errors+=1
        assert errors==1 and len([c for c in commands if c['action']=='run'])==before+1
        # Actual nonqueued stop endpoint can interrupt the queued generator.
        previous_turn=agents.owner_slot(SimpleNamespace(session_hash=fresh.session_hash,username=None)).state.get('turn_id')
        running=fresh.submit('cancel task','model',False,True,[],api_name='/agent_submit')
        deadline=time.monotonic()+5
        slot=agents.owner_slot(SimpleNamespace(session_hash=fresh.session_hash,username=None))
        while time.monotonic()<deadline and (not slot.running or slot.state.get('turn_id') in (None,previous_turn)):
            time.sleep(.05)
        fresh.predict([],api_name='/agent_cancel')
        running.result()
        confirmed=fresh.predict([],api_name='/agent_recover')
        assert 'cancelled' in confirmed[1]
        print('PASS: real Gradio build/HTTP, tasks, follow-up, two browsers, downloads, recovery, cleanup, double-click and remote cancel — 0 OpenAI requests.')
    finally:
        demo.close()

if __name__=='__main__': main()
