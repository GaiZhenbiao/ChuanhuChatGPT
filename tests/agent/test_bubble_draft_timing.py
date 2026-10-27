"""Draft display receipt is independent from remote submission confirmation."""
import ast
import html
import json
import re
import subprocess
import threading
from pathlib import Path
import gradio as gr
import pytest
from agent_fixtures import env, request
from test_input_model import staged
from modules.agent.ui import AgentPanel
from modules.model_capabilities import CapabilityUI

@pytest.mark.parametrize('failure',[False,True])
def test_first_bubble_frame_contains_draft_receipt_before_attachment_submission(env,tmp_path,monkeypatch,failure):
    model,paths,service,calls=staged(env,tmp_path,monkeypatch)
    entered,release=threading.Event(),threading.Event()
    original=env.agents.worker_messages
    def worker(command):
        if command['action']=='prepare_inputs':
            entered.set();assert release.wait(5)
            if failure:
                yield {'type':'error','message':'Synthetic environment disconnected; no turn submitted'}
                return
        yield from original(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with gr.Blocks(analytics_enabled=False) as app:
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components();panel.input_components()
        cap=CapabilityUI([],gr.Dropdown(),gr.HTML(),gr.Button(),gr.Button());cap.wire(None,None)
    text='Synthetic visible message'
    envelope=panel.wrap_transfer(env.wrappers['transfer_input'])(text,model,agent_files=paths,request=request())[0]
    iterator=panel.wrap_predict(env.wrappers['predict'],cap,compact=True)(model,envelope,[],agent_files=paths,request=request())
    try:
        first=next(iterator)
        assert first[0] and text in str(first[0][0][0])
        marker=first[2+len(panel.stream_outputs)+cap.stream_outputs.index(cap.marker)]
        if isinstance(marker,dict):marker=marker['value']
        payload=json.loads(html.unescape(re.search(r'data-model-capabilities="([^"]+)"',marker).group(1)))
        assert payload['submitted_draft']=={'token':envelope['token'],'conversation':model._conversation_id,'text':text}
        assert not model._draft_submitted and not model._draft_acknowledged
        assert entered.wait(3)
        release.set();remaining=list(iterator)
        if failure:
            assert not model._draft_submitted and not model.history
            assert not model._pending_upload_paths
            assert model._input_context and model._input_stager is not None
            assert model._display==[[text,'']] and model.chatbot==[[text,'']]
            assert text in str(remaining[-1][0])
            # A later manually submitted request uses the kept display signature;
            # this failed text remains outside the provider history reference.
            monkeypatch.setattr(env.agents,'worker_messages',original)
            second=panel.wrap_transfer(env.wrappers['transfer_input'])('Next manual request',model,agent_files=[],request=request())[0]
            list(panel.wrap_predict(env.wrappers['predict'],cap,compact=True)(model,second,model.chatbot,agent_files=[],request=request()))
            run=next(command for command in calls if command['action']=='run')
            assert text not in str(run.get('history_reference'))
            assert model._draft_token==second['token']
    finally:
        release.set();iterator.close()
        task=getattr(model,'_background_task',None)
        if task:task.thread.join(5)
        app.close()


@pytest.mark.parametrize('component,event',[('user_input','submit'),('submitBtn','click')])
def test_real_main_send_and_enter_js_capture_draft_for_existing_browser_guard(component,event):
    root=Path(__file__).resolve().parents[2]
    tree=ast.parse((root/'ChuanhuChatbot.py').read_text())
    entry=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr==event and isinstance(n.func.value,ast.Name) and n.func.value.id==component and any(k.arg is None and isinstance(k.value,ast.Name) and k.value.id=='transfer_input_args' for k in n.keywords))
    assert entry
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='transfer_input_args' for t in n.targets))
    source=next(k.value.value for k in assignment.value.keywords if k.arg=='js')
    guard=(root/'web_assets/javascript/agent-inputs.js').read_text()
    script='''const vm=require('vm'),assert=require('assert');let input={value:'first',dispatchEvent(){}};const handlers={};const window={chuanhuInputConversation:()=> 'conv',chuanhuDraftEditRevision:0};const document={readyState:'complete',documentElement:{},addEventListener:(n,f)=>handlers[n]=f,querySelector:s=>s==='#user-input-tb textarea'?input:null};const context={window,document,Event:class{},MutationObserver:class{observe(){}}};vm.createContext(context);
'''+ 'vm.runInContext('+json.dumps(guard)+',context);const submit=vm.runInContext('+json.dumps('('+source+')')+',context);'+'''
submit('first',null,'model','default',0,[],...Array(14).fill(null));
assert.strictEqual(window.chuanhuAgentPendingDraft.text,'first');window.chuanhuClearSubmittedDraft({token:'one',conversation:'conv',text:'first'});assert.strictEqual(input.value,'');
input.value='second';submit('second',null,'model','default',0,[],...Array(14).fill(null));input.value='next draft';handlers.input({target:{matches:()=>true}});window.chuanhuClearSubmittedDraft({token:'two',conversation:'conv',text:'second'});assert.strictEqual(input.value,'next draft');
'''
    result=subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
