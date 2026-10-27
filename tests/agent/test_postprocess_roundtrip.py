"""Production postprocess idempotence; strict receipts never waive submit guards."""
import __future__
import ast
import asyncio
from base64 import b64decode,b64encode
from copy import deepcopy
import json
from pathlib import Path
import re
from threading import Event
from types import MethodType
import gradio as gr
from gradio.components.chatbot import ChatbotData,FileMessage
from gradio.data_classes import FileData
from gradio.state_holder import SessionState
from gradio_client import utils as client_utils
import pytest
from agent_fixtures import env,select,request
from modules.agent.message_files import MessageFileProjection,render_projection,decode_rows,_marker
from modules.agent.ui import AgentPanel
from modules.model_capabilities import CapabilityUI
from test_runtime import message
from test_single_reply_bubble import model,update,command

ROOT=Path(__file__).resolve().parents[2]


def functions(path,names,namespace):
    tree=ast.parse(path.read_text());nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec',flags=__future__.annotations.compiler_flag),namespace)
    return namespace


def converters(root=ROOT):
    return functions(root/'modules/utils.py',{'escape_markdown','clip_rawtext','convert_user_before_marked','convert_bot_before_marked'},{'re':re})


def production_postprocessors(namespace):
    return functions(ROOT/'modules/overwrites.py',{'postprocess','postprocess_chat_messages'},dict(namespace,ChatbotData=ChatbotData,FileMessage=FileMessage,FileData=FileData,client_utils=client_utils))


def postprocess(rows,namespace):
    fn=production_postprocessors(namespace)['postprocess_chat_messages']
    return [[fn(None,u,'user'),fn(None,a,'bot')] for u,a in rows]


def projection(raw=None,conversation='chat',body=False):
    rows=[['question',raw]]
    p=MessageFileProjection(rows=[['question',raw if raw is not None else '']],row_anchors={0:'am-'+'1'*64},artifact_anchors={},view_only_rows=set(),conversation_id=conversation,_original_rows=deepcopy(rows))
    p.cell_segments={(0,1):[{'markup':'<div class="agent-history-activity"><details><summary>Tool</summary><pre>&lt;raw&gt; &amp; complete</pre></details></div>'}]+([{'text':raw}] if body and raw else [])}
    return p


@pytest.mark.parametrize('raw',[None,'',' \n','<b>body & "quoted"</b> 👩🏽\u200d💻\n```html\n<span>raw</span>\n```'])
@pytest.mark.parametrize('conversation',['chat','quote & <scope> "\' entity &amp;'])
def test_real_formatters_repeat_postprocess_exactly_and_raw_copy_remains_original(raw,conversation):
    namespace=converters();p=projection(raw,conversation,body=bool(raw and raw.strip()))
    output=render_projection(p,namespace['convert_user_before_marked'],namespace['convert_bot_before_marked'])
    if raw is None or not raw.strip():assert '<div class="agent-format-receipt hideM" hidden>' in output[0][1]
    assert decode_rows(output,conversation)==p._original_rows
    for _ in range(4):
        repeated=postprocess(output,namespace)
        assert repeated==output and decode_rows(repeated,conversation)==p._original_rows
        output=repeated
    copy=output[0][1].split('</div>',1)[0]
    assert 'agent-message-anchor' not in copy and 'data-agent-message-raw' not in copy


def test_generated_hidden_format_structure_survives_without_removing_loader_state(env):
    m=model(env);update(m,[message('u','question',role='user'),command()],history_authoritative=True)
    m._state['outcome']='cancelled';m._running=False;m._sync_items(m._cloud_items)
    namespace=converters();panel=AgentPanel(namespace['convert_user_before_marked'],namespace['convert_bot_before_marked'])
    rendered=panel.render_chat(m,m._display)
    assert '<div class="agent-format-receipt hideM" hidden>' in rendered[-1][1] and 'agent-reply-state' in rendered[-1][1]
    assert postprocess(rendered,namespace)==rendered
    assert decode_rows(postprocess(rendered,namespace),m._conversation_id)==m._display==[['question',None]]


def rewrite(value,changes):
    match=re.search(r'data-agent-message-raw="([^"]+)"',value);payload=json.loads(b64decode(match.group(1)));payload.update(changes)
    return value.replace(match.group(1),b64encode(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).decode())


@pytest.mark.parametrize('variant',['prefix','suffix','role','attributes','hash','raw_type','schema','version','base64','noncanonical'])
def test_invalid_marker_does_not_gain_formatter_passthrough_or_decode_permission(variant):
    ns=converters();original=render_projection(projection(),ns['convert_user_before_marked'],ns['convert_bot_before_marked'])[0][1]
    variants={'prefix':'changed'+original,'suffix':original+'trailing','role':original.replace('agent-message-anchor','agent-message-raw'),'attributes':original.replace('hidden="hidden"','hidden'),'hash':rewrite(original,{'rendered_sha256':'0'*64}),'raw_type':rewrite(original,{'raw':{}}),'schema':rewrite(original,{'unexpected':'value'}),'version':rewrite(original,{'v':True}),'base64':re.sub(r'data-agent-message-raw="[^"]+"','data-agent-message-raw="x"',original),'noncanonical':original.replace('data-agent-message-cell="assistant"','data-agent-message-cell="user"')}
    value=variants[variant]
    formatted=ns['convert_bot_before_marked'](value)
    # The formatter's pre-existing md structure shortcut is unchanged;
    # invalid metadata cannot grant decoder permission in either case.
    assert '<div class="md-message">' in formatted
    assert decode_rows([[None,formatted]],'chat')==[[None,formatted]]


@pytest.mark.parametrize('mode',['foreign','valid_but_wrong_raw','changed_prefix'])
def test_valid_receipt_format_detection_never_waives_actual_model_signature_guard(env,mode):
    m=model(env);update(m,[message('u','question',role='user'),command()],history_authoritative=True)
    m._state['outcome']='cancelled';m._running=False;m._sync_items(m._cloud_items)
    ns=converters();visible=AgentPanel(ns['convert_user_before_marked'],ns['convert_bot_before_marked']).render_chat(m,m._display)
    match=re.search(r'data-agent-message-raw="([^"]+)"',visible[0][1]);payload=json.loads(b64decode(match.group(1)))
    if mode=='foreign':payload['conversation']='foreign'
    if mode=='valid_but_wrong_raw':payload['raw']='forged answer'
    marker=re.search(r'<span class="agent-message-anchor".*?</span>$',visible[0][1]).group()
    modified=visible[0][1][:-len(marker)]+_marker(payload)
    if mode=='changed_prefix':modified='changed'+modified
    visible[0][1]=ns['convert_bot_before_marked'](modified)
    with pytest.raises(gr.Error,match='聊天内容已变化'):
        list(m.predict('must not submit',visible))


@pytest.mark.parametrize('case',json.loads((ROOT/'tests/agent/fixtures/ordinary_formatter_before_postprocess_fix.json').read_text())['cases'])
def test_ordinary_and_marker_looking_raw_text_formatting_is_identical_to_previous_version(case):
    current=converters()
    assert current['convert_bot_before_marked'](case['raw'])==case['bot']
    assert current['convert_user_before_marked'](case['raw'])==case['user']


def test_real_gradio_cancel_tool_only_then_resend_same_chat_and_normal_multiround(env,monkeypatch):
    m=select(env);cancel=Event();calls=[];items=[];turns=[]
    def worker(command_payload):
        action=command_payload['action'];calls.append((action,command_payload.get('prompt'),command_payload.get('session_id')))
        if action=='cancel':
            cancel.set();yield dict(type='result',outcome='cancel_requested');return
        if action=='download':yield dict(type='result',artifacts=[]);return
        assert action=='run'
        turn='t'+str(len(turns)+1);turns.append(turn);prompt=command_payload['prompt']
        user=message('u'+turn,prompt,turn,role='user');items.append(user)
        payload=dict(session_id='sess_postprocess',turn_id=turn,submission_started=True)
        if prompt=='cancel-tool-only':
            item=command('cmd2',turn=turn);item['command']='cancel command';items.append(item)
            yield dict(type='progress',outcome='in_progress',history_authoritative=True,items=deepcopy(items),**payload)
            assert cancel.wait(5),'production stop must release synthetic worker'
            items[-1]=dict(item,status='cancelled')
            yield dict(type='result',outcome='cancelled',sync_complete=True,items=deepcopy(items),**payload)
        else:
            yield dict(type='progress',outcome='in_progress',history_authoritative=True,items=deepcopy(items),**payload)
            items.append(message('a'+turn,'answer '+prompt,turn))
            yield dict(type='result',outcome='completed',sync_complete=True,items=deepcopy(items),**payload)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    ns=converters();production=production_postprocessors(ns)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();text=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();button=gr.Button();selector=gr.Dropdown();marker=gr.HTML()
        chat.postprocess=MethodType(production['postprocess'],chat)
        chat._postprocess_chat_messages=MethodType(production['postprocess_chat_messages'],chat)
        caps=CapabilityUI([],selector,marker);caps.wire(current,chat)
        panel=AgentPanel(ns['convert_user_before_marked'],ns['convert_bot_before_marked']);panel.selectors();panel.settings_components();panel.output_components()
        button.click(panel.wrap_predict(env.wrappers['predict'],caps),[current,text,chat],[chat,status,*panel.outputs,*caps.outputs])
    state=SessionState(app);state[current._id]=m;index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='predict_with_ui')
    conversation=m._conversation_id
    async def send_view(prompt,visible,stop=False):
        result=await app.process_api(index,[None,prompt,visible],state=state,request=request());stopped=False
        while True:
            frame=result['data'][0]
            if isinstance(frame,list):visible=frame
            elif isinstance(frame,dict) and 'value' in frame:visible=frame['value']
            if stop and not stopped and 'cancel command' in str(visible):
                m.interrupt();stopped=True
            if not result['is_generating']:break
            result=await app.process_api(index,[None,prompt,visible],state=state,request=request(),iterator=result['iterator'])
        assert decode_rows(visible,m._conversation_id)==m.chatbot==m._display
        assert m._conversation_id==conversation
        if stop:assert stopped and m._state['outcome']=='cancelled' and m.chatbot[-1][1] is None
        return visible
    async def exercise():
        visible=await send_view('completed-before',[])
        visible=await send_view('cancel-tool-only',visible,stop=True)
        assert 'agent-reply-state' in visible[-1][1] and '<div class="agent-format-receipt hideM" hidden>' in visible[-1][1]
        visible=await send_view('resend-original',visible)
        assert len(m.chatbot)==3 and m.chatbot[1]==['cancel-tool-only',None] and m.chatbot[2][1]=='answer resend-original'
        visible=await send_view('normal-followup',visible)
        assert len(m.chatbot)==4 and m._state['outcome']=='completed' and turns==['t1','t2','t3','t4']
        assert all(sid=='sess_postprocess' for action,prompt,sid in calls if action=='run' and prompt!='completed-before')
        assert all('agent-message' not in str(item.get('content')) for item in m.history)
        saved=json.loads((env.history_dir/m.history_file_path).read_text());assert saved['chatbot']==m.chatbot
    try:asyncio.run(exercise())
    finally:app.close()


def test_actual_ordinary_base_model_two_rounds_with_production_postprocessor(env):
    ordinary=select(env,name='GPT3.5 Turbo');ns=converters();production=production_postprocessors(ns)
    with gr.Blocks(analytics_enabled=False) as app:
        text=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();button=gr.Button()
        chat.postprocess=MethodType(production['postprocess'],chat)
        chat._postprocess_chat_messages=MethodType(production['postprocess_chat_messages'],chat)
        def ordinary_send(prompt,rows,request:gr.Request):
            yield from env.wrappers['predict'](ordinary,prompt,rows,request=request)
        button.click(ordinary_send,[text,chat],[chat,status])
    state=SessionState(app);index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='ordinary_send')
    async def exercise():
        visible=[]
        for prompt in ('ordinary <b>& first</b>','ordinary followup'):
            result=await app.process_api(index,[prompt,visible],state=state,request=request())
            while True:
                frame=result['data'][0]
                if isinstance(frame,list):visible=frame
                elif isinstance(frame,dict) and 'value' in frame:visible=frame['value']
                if not result['is_generating']:break
                result=await app.process_api(index,[prompt,visible],state=state,request=request(),iterator=result['iterator'])
            assert 'Ordinary synthetic response' in visible[-1][1]
            assert postprocess(visible,ns)==visible
            assert 'agent-message-' not in str(visible)+str(ordinary.history)
        assert len(visible)==2
    try:asyncio.run(exercise())
    finally:app.close()


@pytest.mark.parametrize('prefix',[
    '<img src=x onerror="alert(1)"><script>alert(2)</script>',
    '<div class="agent-history-activity"><img src=x onerror="alert(1)"></div>',
    '<div class="agent-format-receipt hideM" hidden><img src=x onerror="alert(1)"></div>',
])
def test_selfconsistent_public_hash_never_grants_new_arbitrary_html_passthrough(prefix):
    import hashlib
    ns=converters();payload=dict(v=1,conversation='chat',key='am-'+'1'*64,role='assistant',raw=None,view_only=False,rendered_sha256=hashlib.sha256(prefix.encode()).hexdigest())
    forged=prefix+_marker(payload)
    assert decode_rows([[None,forged]],'chat')==[[None,None]],'public hash is not origin authentication'
    formatted=ns['convert_bot_before_marked'](forged)
    assert formatted!=forged,'forged public checksum cannot create a new HTML passthrough branch'
    assert decode_rows([[None,formatted]],'chat')==[[None,formatted]]
    assert '&#60;img' in formatted.split('<div class="md-message">',1)[0]
