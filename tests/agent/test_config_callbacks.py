import asyncio
from copy import deepcopy
import threading
import pytest
import gradio as gr
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel
from agent_fixtures import env,select,complete,request


def config_values(network):
    return [network,True,True,'live','',True,False,True,True,[],'[]']


def test_latest_ui_configuration_is_frozen_with_send_before_delayed_callbacks(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();chat=gr.Chatbot();status=gr.Markdown();text=gr.Textbox();question=gr.State();send=gr.Button();stop=gr.Button()
        panel=AgentPanel();panel.input_components();panel.selectors();panel.settings_components();panel.output_components();panel.wire(current,chat,status)
        inputs=[text,current,panel.model,panel.reasoning,panel.choice_revision,panel.input_files,*panel.config_inputs,gr.Textbox(),panel.config_target,panel.tool_revision]
        send.click(panel.wrap_transfer(env.wrappers['transfer_input']),inputs,[question,text,send,stop])
    state=SessionState(app);state[current._id]=model
    choose=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='choose_tools')
    transfer=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='transfer_input')
    enter=threading.Event();release=threading.Event();original=model.stage_agent_tools
    def delayed(value,revision,target):
        if revision==1: enter.set();assert release.wait(5)
        return original(value,revision,target)
    monkeypatch.setattr(model,'stage_agent_tools',delayed)
    async def exercise():
        first=asyncio.create_task(app.process_api(choose,[None,*config_values(False),1,model._conversation_id],state=state,request=request()))
        assert await asyncio.to_thread(enter.wait,3)
        await app.process_api(choose,[None,*config_values(True),2,model._conversation_id],state=state,request=request())
        release.set();older=await first
        assert model._tool_settings['network'] is True
        assert all(isinstance(item,dict) and 'value' not in item for item in older['data'])
        # The actual whole widget snapshot on Send wins, even before another
        # input callback has run. It freezes under the same lock as reservation.
        await app.process_api(transfer,['run frozen',None,'gpt-6-astra','default',0,[],*config_values(False),'UI instructions',model._conversation_id,2],state=state,request=request())
        envelope=state[question._id]
        with pytest.raises(gr.Error,match='当前任务仍在运行'):
            await app.process_api(choose,[None,*config_values(True),3,model._conversation_id],state=state,request=request())
        assert model._tool_settings['network'] is False and model.system_prompt=='UI instructions'
        list(env.wrappers['predict'](model,envelope,[],request=request()))
        command=next(command for command in calls if command['action']=='run')
        assert command['tool_settings']['network'] is False and command['instructions']=='UI instructions'
        fresh=select(env,browser='another')
        assert fresh._tool_settings['network'] is True
    try:asyncio.run(exercise())
    finally:release.set();app.close()
