"""Single history publication and stable completed-artifact presentation."""
from copy import deepcopy
from types import SimpleNamespace
from threading import Event
import json
import logging
import gradio as gr
import pytest
from agent_fixtures import env, complete, select, send, request
from test_ui import panel_app
from modules.agent.ui import AgentPanel
from modules.model_capabilities import CapabilityUI


def controls(app, panel):
    with app:
        selector=gr.Dropdown();marker=gr.HTML();submit=gr.Button();cancel=gr.Button()
        panel.history_list=gr.Radio()
        legacy=[gr.State(),selector,*[gr.Textbox() for _ in range(22)]]
        caps=CapabilityUI([('sampling',legacy[6],None)],selector,marker,submit,cancel)
        caps.wire(legacy[0],legacy[4])
    return legacy,caps


def test_model_projection_preserves_placeholder_label_and_avatar(env):
    model=select(env);app,panel,state=panel_app(model)
    legacy,caps=controls(app,panel)
    legacy=legacy[:10]
    update=gr.update(value=model.chatbot,label='OpenAI Agent',placeholder='distinct-agent-logo',avatar_images=['user.svg','agent.svg'])
    result=[model,'',update,*[gr.update() for _ in range(7)]]
    callback=panel.wrap_model_change(lambda:result,caps,legacy)
    outputs=list(dict.fromkeys([legacy[0],*panel.outputs,*caps.stream_outputs,*legacy[1:]]))
    rendered=callback()[outputs.index(legacy[2])]
    for key in ('label','placeholder','avatar_images'):assert rendered[key]==update[key]
    app.close()


def test_history_first_response_contains_projected_chat_and_files(env,monkeypatch):
    complete(env,monkeypatch,True);model=select(env);send(env,model)
    app,panel,state=panel_app(model);legacy,caps=controls(app,panel)
    raw=[model,gr.update(),gr.update(),gr.update(),gr.update(value=model.chatbot,label='OpenAI Agent'),*[gr.update() for _ in range(19)]]
    callback=panel.wrap_history_load(lambda *a,**kw:tuple(raw),caps,legacy_outputs=legacy)
    outputs=list(dict.fromkeys([*legacy,*panel.outputs,*caps.outputs,panel.history_list]))
    values=callback(model,'synthetic',request())
    assert len(values)==len(outputs) and len(set(outputs))==len(outputs)
    assert 'agent-message-anchor' in values[outputs.index(legacy[4])]['value'][0][1]
    assert 'model-file-card' in values[outputs.index(panel.artifacts.list)]['value']
    assert values[outputs.index(panel.config_target)]==model._conversation_id
    assert values[outputs.index(legacy[4])]['label']=='OpenAI Agent'
    assert values[outputs.index(legacy[6])]['visible'] is False
    app.close()


def test_same_turn_ready_artifact_survives_preparing_metadata(env,monkeypatch):
    calls,file=complete(env,monkeypatch,True);model=select(env);send(env,model)
    old=deepcopy(model._artifacts[0]);metadata={k:v for k,v in old.items() if k!='path'};metadata['status']='preparing'
    model._merge_artifacts([metadata]);assert model._artifacts[0]['status']=='ready' and model._artifacts[0]['path']==str(file)
    metadata['turn_id']='different-turn';model._merge_artifacts([metadata]);assert model._artifacts[0]['status']=='preparing'
    model._artifacts=[old];file.unlink();metadata['turn_id']=old['turn_id'];model._merge_artifacts([metadata]);assert model._artifacts[0]['status']=='preparing'


def test_read_only_completed_sync_keeps_send_visible_and_execution_locked(env):
    from modules.agent.tasks import TaskRegistry
    model=select(env);model._state.update(generation='g',session_id='session',turn_id='turn',outcome='completed');model._needs_sync=True
    app,panel,state=panel_app(model);legacy,caps=controls(app,panel)
    entered=Event();release=Event();registry=TaskRegistry()
    def observe():
        entered.set();release.wait(3);yield model.chatbot,''
    task=registry.start(model,observe,read_only=True)
    try:
        assert entered.wait(2)
        values=caps.stream_values(model)
        assert values[caps.stream_outputs.index(caps.submit)]['visible'] is True
        assert values[caps.stream_outputs.index(caps.submit)]['interactive'] is False
        assert values[caps.stream_outputs.index(caps.cancel)]['visible'] is False
        with pytest.raises(gr.Error):model._assert_idle()
        model._state['outcome']='in_progress'
        assert caps.stream_values(model)[caps.stream_outputs.index(caps.cancel)]['visible'] is True
    finally:release.set();task.thread.join(4);app.close()


def test_observer_does_not_republish_unchanged_chat(env,monkeypatch):
    from modules.agent.tasks import TASKS
    model=select(env);app,panel,state=panel_app(model)
    monkeypatch.setattr(TASKS,'find',lambda *a:SimpleNamespace(subscribe=lambda view:iter([(deepcopy(view.chatbot),'done')]*2)))
    frames=list(panel.observe_history(model,request=request()))
    assert all(frame[0]==gr.update() for frame in frames)
    app.close()


def test_loaded_history_observer_and_boundary_do_not_repaint_controls(env, monkeypatch):
    from modules.agent.tasks import TASKS
    model=select(env);app,panel,state=panel_app(model);legacy,caps=controls(app,panel)
    with app: panel.wire(legacy[0],legacy[4],legacy[23],caps)
    model._history_ui_projection_visit=model.agent_choice_target
    monkeypatch.setattr(TASKS,'find',lambda *a:SimpleNamespace(subscribe=lambda view:iter([(deepcopy(view.chatbot),'done')]*2)))
    frames=list(panel.observe_history(model,request=request()))
    assert all(value==gr.update() for frame in frames for index,value in enumerate(frame) if index!=1)
    assert all(value==gr.update() for value in panel.history_boundary_values(caps)(model,request()))
    app.close()


def test_history_capability_visibility_preserves_ordinary_saved_parameter(env):
    model=select(env,name='GPT3.5 Turbo');app,panel,state=panel_app(model);legacy,caps=controls(app,panel)
    raw=[model,*[gr.update() for _ in range(23)]];raw[4]=gr.update(value=[],label='GPT3.5 Turbo');raw[6]=gr.update(value=0.25)
    callback=panel.wrap_history_load(lambda *a,**kw:tuple(raw),caps,legacy_outputs=legacy)
    outputs=list(dict.fromkeys([*legacy,*panel.outputs,*caps.outputs,panel.history_list]))
    update=callback(model,'synthetic',request())[outputs.index(legacy[6])]
    assert update['value']==0.25 and update['visible'] is True
    app.close()
