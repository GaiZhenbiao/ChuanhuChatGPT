import asyncio
import gradio as gr
from gradio.state_holder import SessionState
from modules.agent.ui import AgentPanel, i18n
from agent_fixtures import env,select,send,complete,request


def test_sidebar_uses_session_snapshot_and_restores_ordinary_controls(env,monkeypatch):
    complete(env,monkeypatch);model=select(env)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();button=gr.Button();chat=gr.Chatbot();status=gr.Markdown()
        with gr.Tab('对话') as tab:
            panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components()
            with gr.Accordion('Prompt') as prompt_group:
                prompt=gr.Textbox();template=gr.Dropdown(choices=[])
        panel.bind_sidebar(tab,prompt,template,prompt_group,'对话')
        button.click(panel.values,[current],panel.outputs)
    assert panel.discovery.visible is False and panel.programmatic.visible is False
    state=SessionState(app);state[current._id]=model
    def frame():return asyncio.run(app.process_api(0,[None],state=state,request=request()))['data']
    first=frame();assert first[panel.outputs.index(tab)]['label']=='Agent'
    assert not hasattr(panel,'save')
    assert panel.model.label==i18n('ui.toolbox.agent.model') and not panel.settings_status.visible and not panel.availability.visible and not panel.fork.visible
    for component in [panel.network,panel.code,panel.search,panel.browser,panel.screenshots]:
        assert 'switch-checkbox' in component.elem_classes
    assert 'switch-checkbox' not in panel.functions.elem_classes
    for component in [c for c in panel.config_inputs if c not in (panel.discovery,panel.programmatic)]+[prompt,template]:assert first[panel.outputs.index(component)]['interactive']
    for component in (panel.discovery,panel.programmatic):assert first[panel.outputs.index(component)]['interactive'] is False
    model._state['outcome']='uncertain';model._needs_sync=True
    unknown=frame()
    for component in [*panel.config_inputs,prompt,template]:assert unknown[panel.outputs.index(component)]['interactive'] is False
    model._state['outcome']='not_started';model._needs_sync=False
    send(env,model)
    locked=frame()
    for component in [*panel.config_inputs,prompt,template]:assert locked[panel.outputs.index(component)]['interactive'] is False
    for component in [panel.model,panel.reasoning]:assert locked[panel.outputs.index(component)]['interactive'] is True
    assert locked[panel.outputs.index(prompt)]['value']==model._session_settings['instructions']
    model.reset()
    ordinary=select(env,model,name='GPT3.5 Turbo');state[current._id]=ordinary;restored=frame()
    assert restored[panel.outputs.index(tab)]['label']=='对话'
    assert restored[panel.outputs.index(prompt)]['interactive'] is True
    app.close()
