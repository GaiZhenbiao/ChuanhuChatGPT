"""Unified capability gates and the main UI's queued-send target reservation."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
import gradio as gr
import pytest
from gradio.state_holder import SessionState
from modules.model_capabilities import ModelCapabilities, AGENT_CAPABILITIES, CapabilityUI, capabilities, require_capability, reserve_submission
from modules.agent.ui import ArtifactPanel
from agent_fixtures import env, select, send, complete, request


def test_agent_declares_all_unsupported_controls_and_independent_outputs(env):
    model=select(env);caps=capabilities(model)
    for name in ('knowledge','external_websearch','sampling','token_limits','single_turn','output_mode','regenerate','history_delete','history_edit','history_rollback','billing','reply_language'):
        assert not getattr(caps,name)
    assert caps.output_artifacts and caps.agent_tools and caps.input_attachments and caps.sandbox_attachments
    assert caps.message_copy and caps.message_markdown
    ordinary=select(env,name='GPT3.5 Turbo')
    assert capabilities(ordinary).input_attachments and capabilities(ordinary).regenerate


@pytest.mark.parametrize('method,value',[('set_temperature',.7),('set_top_p',.7),('set_n_choices',2),('set_max_tokens',400),('set_token_upper_limit',400),('set_stop_sequence','x'),('set_presence_penalty',1),('set_frequency_penalty',1),('set_logit_bias','a:1'),('set_user_identifier','a'),('set_single_turn',True),('set_streaming',False)])
def test_direct_parameter_bypass_rejected_for_agent(env,method,value):
    model=select(env)
    with pytest.raises(gr.Error):getattr(model,method)(value)
    ordinary=select(env,name='GPT3.5 Turbo');getattr(ordinary,method)(value)


def test_native_visibility_restores_and_hidden_input_values_are_cleared(env):
    agent=select(env);ordinary=select(env,name='GPT3.5 Turbo')
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();upload=gr.File(file_count='multiple');search=gr.Checkbox(value=True,visible=False);retry=gr.Button();selector=gr.Dropdown(choices=['ordinary','agent']);marker=gr.HTML()
        ui=CapabilityUI([('knowledge',upload,[]),('external_websearch',search,False),('regenerate',retry,None)],selector,marker);ui.wire(current,chat)
    hidden=ui.values(agent);assert hidden[0]['visible'] is False and hidden[0]['value']==[] and hidden[1]['value'] is False and hidden[2]['visible'] is False
    restored=ui.values(ordinary);assert restored[0]['visible'] and restored[2]['visible'] and not restored[1]['visible']
    assert 'data-model-capabilities' in restored[-1]
    app.close()


def test_custom_models_use_same_declaration_without_name_checks():
    class Custom:
        ui_capabilities=replace(ModelCapabilities(),regenerate=False,output_artifacts=True)
        _artifacts=[]
    model=Custom()
    with pytest.raises(gr.Error):require_capability(model,'regenerate')
    assert capabilities(model).input_attachments and len(ArtifactPanel.values(model))==4


@pytest.mark.parametrize('name',['GPT3.5 Turbo','OpenAI Agent'])
def test_pending_send_prevents_switch_reset_and_old_queued_redirect(env,monkeypatch,name):
    complete(env,monkeypatch);model=select(env,name=name)
    envelope=reserve_submission(model,'bound input')
    assert select(env,model,name='OpenAI Agent' if name!='OpenAI Agent' else 'GPT3.5 Turbo') is model
    with pytest.raises(gr.Error):model.reset()
    other=select(env,name='GPT3.5 Turbo')
    with pytest.raises(gr.Error):list(env.wrappers['predict'](other,envelope,[],request=request()))
    output=list(env.wrappers['predict'](model,envelope,[],request=request()))
    assert output[-1][0][-1][0]=='bound input' and model._pending_send is None


def test_stop_pending_send_never_launches_worker(env,monkeypatch):
    calls=[];monkeypatch.setattr(env.agents,'worker_messages',lambda command:calls.append(command) or iter([]))
    model=select(env);envelope=reserve_submission(model,'not submitted')
    assert '尚未提交' in env.wrappers['interrupt'](model,request=request())
    with pytest.raises(gr.Error):list(env.wrappers['predict'](model,envelope,[],request=request()))
    assert not calls and not model.history


def test_real_transfer_predict_callback_chain_preserves_target(env,monkeypatch):
    complete(env,monkeypatch);model=select(env)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();question=gr.State();input_box=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown();submit=gr.Button();cancel=gr.Button()
        submit.click(env.wrappers['transfer_input'],[input_box,current],[question,input_box,submit,cancel]).then(env.wrappers['predict'],[current,question,chat],[chat,status])
    state=SessionState(app);state[current._id]=model
    async def exercise():
        req=gr.Request(session_hash='ui')
        await app.process_api(0,['first',None],state=state,request=req)
        assert model._pending_send and isinstance(state[question._id],dict)
        assert select(env,model,name='GPT3.5 Turbo') is model
        result=await app.process_api(1,[None,None,[]],state=state,request=req)
        while result['is_generating']:
            result=await app.process_api(1,[None,None,[]],state=state,request=req,iterator=result['iterator'])
    try:asyncio.run(exercise())
    finally:app.close()
    assert model.chatbot==[['first','Agent synthetic answer']] and model._pending_send is None


def test_custom_dom_controls_follow_capabilities():
    import shutil,subprocess
    from pathlib import Path
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed for the isolated DOM contract test')
    result=subprocess.run([node,'tests/javascript/model-capabilities.test.cjs'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
