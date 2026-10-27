"""Real SDK event shapes and post-terminal races, using synthetic data only."""
from copy import deepcopy
import logging
from types import SimpleNamespace
import pytest
from agent_fixtures import env, select, send, request
from modules.agent.runtime import TurnState
from modules.agent.ui import AgentPanel, ArtifactPanel


def test_sdk_done_replaces_partial_and_keeps_current_item_identity():
    from openai.types.beta.agent_session_turn_output_text_delta_event import AgentSessionTurnOutputTextDeltaEvent
    from openai.types.beta.agent_session_turn_item_done_event import AgentSessionTurnItemDoneEvent
    state = TurnState('synthetic-session', 'synthetic-turn')
    state.accept(AgentSessionTurnOutputTextDeltaEvent(type='agent.session.turn.output_text.delta', event_id='delta', session_id='synthetic-session', turn_id='synthetic-turn', item_id='answer', output_index=0, content_index=0, delta='Hello'))
    assert state.snapshot()['text'] == 'Hello'
    assert state.snapshot()['items'][0]['turn_id'] == 'synthetic-turn'
    state.accept(AgentSessionTurnItemDoneEvent(type='agent.session.turn.item.done', event_id='done', session_id='synthetic-session', turn_id='synthetic-turn', output_index=0, item=dict(id='answer', type='message', role='assistant', turn_id='synthetic-turn', status='completed', content=[dict(type='output_text', text='Hello world', annotations=[])])))
    assert state.snapshot()['text'] == 'Hello world'
    state.accept(dict(type='agent.session.turn.completed', session_id='synthetic-session', turn_id='synthetic-turn'))
    assert state.snapshot()['text'] == 'Hello world'


def test_same_turn_items_restore_one_reply_and_file_anchor(env):
    model = select(env)
    items = [dict(id='user',type='message',role='user',turn_id='turn',content=[dict(type='input_text',text='synthetic task')]),dict(id='commentary',type='message',role='assistant',turn_id='turn',content=[dict(type='output_text',text='Working')]),dict(id='final',type='message',role='assistant',turn_id='turn',content=[dict(type='output_text',text='Result')])]
    model._sync_items(items)
    model._state.update(session_id='session',turn_id='turn')
    model._artifacts=[dict(id='file',session_id='session',turn_id='turn',name='synthetic.txt',size=5,status='preparing')]
    assert model._display == [['synthetic task','Working\n\nResult']]
    from modules.agent.ui import message_file_projection
    projected = message_file_projection(model)
    assert projected.rows == model._display and not projected.view_only_rows
    assert projected.artifact_anchors['file'] == projected.row_anchors[0]


def test_terminal_releases_controls_before_download_and_logs_full_reply_once(env,monkeypatch,caplog):
    model=select(env); observed=[];text='Synthetic final\n'+('full reply '*500)
    def worker(command):
        if command['action']=='run':
            yield dict(type='progress',session_id='session',turn_id='turn',outcome='completed',text=text)
            observed.append(('after_terminal',model._running))
            yield dict(type='result',session_id='session',turn_id='turn',outcome='completed',text=text)
        elif command['action']=='download':
            observed.append(('download',model._running))
            yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    with caplog.at_level(logging.INFO):send(env,model)
    assert observed==[('after_terminal',False),('download',False)]
    logs=[r.getMessage() for r in caplog.records if r.getMessage().startswith('回答为：')]
    assert logs==['回答为：'+text]


def test_stream_updates_do_not_rebuild_dropdown_choices_or_open_panel(env):
    import gradio as gr
    model=select(env)
    with gr.Blocks(analytics_enabled=False):
        panel=AgentPanel()
        with gr.Accordion('Model') as panel.accordion:panel.selectors()
        panel.settings_components();panel.output_components()
    values=panel.values(model,include_config=False)
    for component in [panel.model,panel.reasoning]:
        value=values[panel.outputs.index(component)]
        assert 'value' not in value and 'choices' not in value
    assert values[panel.outputs.index(panel.accordion)]==gr.update()
