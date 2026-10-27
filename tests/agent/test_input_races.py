import asyncio
import json
from pathlib import Path
import subprocess
import threading
import gradio as gr
from gradio.state_holder import SessionState
from agent_fixtures import env, select, request
from modules.agent.input_files import AgentInputFiles
from modules.agent.ui import AgentPanel


def make_panel(model):
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();status=gr.Markdown()
        panel=AgentPanel();panel.input_components();panel.selectors();panel.output_components();panel.settings_components();panel.wire(current,chat,status)
    state=SessionState(app);state[current._id]=model
    fns={fn.fn.__name__:i for i,fn in enumerate(app.fns) if fn.fn}
    return app,panel,state,current,fns


def data(path): return {'path':str(path),'orig_name':path.name,'meta':{'_type':'gradio.FileData'}}


def test_late_upload_keeps_original_conversation_after_new_upload_starts(env,tmp_path,monkeypatch):
    old=select(env);old_target=old._conversation_id
    app,panel,state,current,fns=make_panel(old)
    ordinary=select(env,old,name='GPT3.5 Turbo')
    model=select(env,ordinary);state[current._id]=model
    new_target=model._conversation_id
    root=Path(gr.utils.get_upload_folder());folder=root/('review-'+new_target);folder.mkdir(parents=True)
    old_file=folder/'old-private.txt';old_file.write_text('synthetic prior conversation attachment')
    new_file=folder/'new.txt';new_file.write_text('synthetic new conversation attachment')
    upload_js=app.get_config_file()['dependencies'][fns['upload_files']]['js']
    script=r'''
const fs=require('fs'),vm=require('vm');const input=JSON.parse(fs.readFileSync(0,'utf8'));
let change,current=input.oldTarget;
const document={readyState:'complete',documentElement:{},addEventListener:(name,fn)=>{if(name==='change')change=fn;},querySelector:()=>null};
const window={chuanhuInputConversation:()=>current};
const context={window,document,MutationObserver:class{observe(){}}};
vm.createContext(context);vm.runInContext(fs.readFileSync('web_assets/javascript/agent-inputs.js','utf8'),context);
change({composedPath:()=>[{matches:()=>true,files:[{name:'old-private.txt'}]}]});
// Switching ordinary -> Agent recreates the interactive upload child; a new
// selection occurs before the old asynchronous upload callback is delivered.
current=input.newTarget;
change({composedPath:()=>[{matches:()=>true,files:[{name:'new.txt'}]}],preventDefault(){},stopImmediatePropagation(){}});
context.upload=vm.runInContext('('+input.uploadJS+')',context);
const late=context.upload(null,input.files,input.oldTarget);
process.stdout.write(JSON.stringify(late));
'''
    result=subprocess.run(['node','-e',script],input=json.dumps({'oldTarget':old_target,'newTarget':new_target,'files':[data(old_file)],'uploadJS':upload_js}),text=True,capture_output=True,check=True)
    callback_inputs=json.loads(result.stdout)
    try:
        asyncio.run(app.process_api(fns['upload_files'],callback_inputs,state=state,request=gr.Request(session_hash='review')))
        assert not model._pending_upload_paths, model._pending_upload_paths
    finally: app.close()


def test_older_upload_response_cannot_remove_newer_added_file(env,tmp_path,monkeypatch):
    model=select(env);app,panel,state,current,fns=make_panel(model)
    root=Path(gr.utils.get_upload_folder());folder=root/('review-'+model._conversation_id);folder.mkdir(parents=True)
    one=folder/'one.txt';one.write_text('synthetic one')
    two=folder/'two.txt';two.write_text('synthetic two')
    captured=threading.Event();release=threading.Event()
    original=app.fns[fns['upload_files']].fn
    def delay_response(model,files,target,request:gr.Request):
        iterator=original(model,files,target,request)
        result=next(iterator)
        if len(files)==1 and Path(str(files[0])).name=='one.txt':
            captured.set();assert release.wait(5)
        yield result
        yield from iterator
    app.fns[fns['upload_files']].fn=delay_response
    async def exercise():
        req=gr.Request(session_hash='review')
        first=asyncio.create_task(app.process_api(fns['upload_files'],[None,[data(one)],model._conversation_id],state=state,request=req))
        await asyncio.to_thread(captured.wait,3);assert captured.is_set()
        newer=await app.process_api(fns['upload_files'],[None,[data(two)],model._conversation_id],state=state,request=req)
        release.set();older=await first
        assert len(model._pending_upload_paths)==2
        # The old output arrives last. Gradio File's value change triggers the
        # actual stage_files callback. It must restore the display, not remove B.
        stale_value=older['data'][2]['value']
        repaired=await app.process_api(fns['stage_files'],[None,stale_value],state=state,request=req)
        assert len(repaired['data'][0]['value'])==2
    try: asyncio.run(exercise())
    finally: release.set();app.close()
    assert len(model._pending_upload_paths)==2, model._pending_upload_paths


def test_explicit_stable_id_remove_keeps_newer_files_and_rejects_other_chat(env,tmp_path):
    model=select(env);app,panel,state,current,fns=make_panel(model)
    root=tmp_path/'uploads';root.mkdir()
    one=root/'one.txt';one.write_text('synthetic one')
    two=root/'two.txt';two.write_text('synthetic two')
    model._input_stager=AgentInputFiles([root])
    model.stage_input_files([str(one)])
    old_id=model._input_stager.snapshot()[0].input_id
    old_target=model._conversation_id
    model.add_input_files([str(two)],old_target)
    async def exercise():
        req=gr.Request(session_hash='review')
        await app.process_api(fns['remove_files'],[None,json.dumps({'target':old_target,'ids':[old_id]})],state=state,request=req)
        assert model._pending_upload_paths==(str(two),)
        previous_staging = model._input_stager.staging_root
        model.reset()
        assert not previous_staging.exists() and two.exists()
        model._input_stager = AgentInputFiles([root])
        model.stage_input_files([str(two)])
        identifier=model._input_stager.snapshot()[0].input_id
        await app.process_api(fns['remove_files'],[None,json.dumps({'target':old_target,'ids':[identifier]})],state=state,request=req)
        assert model._pending_upload_paths==(str(two),)
    try:asyncio.run(exercise())
    finally:app.close()
