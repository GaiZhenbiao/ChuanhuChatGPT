import importlib.util
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import pytest
import gradio as gr
from modules import extensions, plugin_callbacks as callbacks
from modules.plugin_context import AppContext, ChatContext

ROOT = Path(__file__).resolve().parents[1]


def load_plugin(name):
    path = ROOT/'extensions'/name/'scripts/main.py'
    spec=importlib.util.spec_from_file_location('test_plugin_'+name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    with callbacks.extension_context(name): spec.loader.exec_module(module)
    return module

@pytest.fixture
def agents(tmp_path,monkeypatch):
    callbacks.clear_callbacks()
    module=load_plugin('openai_agents')
    monkeypatch.setattr(module,'JOURNAL_DIR',tmp_path/'journals')
    return module


def request(owner): return SimpleNamespace(session_hash=owner,username='user')


def test_double_click_reserves_one_billable_task(agents,monkeypatch):
    commands=[]
    def messages(command):
        commands.append(command)
        yield {'type':'progress','session_id':'sess_one','turn_id':'turn_one','outcome':'incomplete'}
        yield {'type':'result','session_id':'sess_one','turn_id':'turn_one','outcome':'completed','text':'done'}
    monkeypatch.setattr(agents,'worker_messages',messages)
    first=agents.submit_task('task','model',False,True,{},[],request('a'))
    second=agents.submit_task('task','model',False,True,{},[],request('a'))
    assert next(first)[0]['outcome']=='starting'
    with pytest.raises(gr.Error,match='避免重复发送'): next(second)
    list(first)
    assert len(commands)==1 and commands[0]['session_id'] is None


def test_browser_owners_are_independent(agents,monkeypatch):
    def messages(command):
        yield {'type':'result','session_id':'sess_'+command['prompt'],'turn_id':'turn_one','outcome':'completed','text':command['prompt']}
    monkeypatch.setattr(agents,'worker_messages',messages)
    a=list(agents.submit_task('a','model',False,True,{},[],request('a')))[-1]
    b=list(agents.submit_task('b','model',False,True,{},[],request('b')))[-1]
    assert a[0]['session_id']=='sess_a' and b[0]['session_id']=='sess_b'
    with pytest.raises(gr.Error,match='不属于'): agents.own_state(a[0],request('b'))


def test_followup_clears_old_turn_and_recover_cannot_overwrite(agents,monkeypatch):
    state={'owner':agents.owner_id(request('a')),'session_id':'sess_one','turn_id':'turn_old','model':'model','outcome':'completed'}
    commands=[]
    def messages(command):
        commands.append(command)
        yield {'type':'progress','session_id':'sess_one','turn_id':'turn_new','outcome':'incomplete','text':'new answer'}
        yield {'type':'result','session_id':'sess_one','turn_id':'turn_new','outcome':'completed','text':'new answer'}
    monkeypatch.setattr(agents,'worker_messages',messages)
    job=agents.submit_task('new question','different-model',True,True,state,[['old','old answer']],request('a'))
    starting=next(job)
    assert starting[0]['turn_id'] is None
    recovered=agents.recover(state,[['old','old answer']],request('a'))
    assert recovered[0]['outcome']=='starting' and recovered[1][-1][1]==''
    assert commands==[]
    result=list(job)[-1]
    assert result[0]['turn_id']=='turn_new' and result[1][-1][1]=='new answer'
    assert commands[0]['model']=='model' and not commands[0]['allow_text_tool']


def test_stop_before_submission_sends_no_task(agents,monkeypatch):
    commands=[]
    monkeypatch.setattr(agents,'worker_messages',lambda command: commands.append(command) or iter([]))
    job=agents.submit_task('task','model',False,True,{},[],request('a'))
    next(job)
    stopped=agents.cancel({},[],request('a'))
    assert stopped[0]['outcome']=='cancel_requested'
    result=list(job)[-1]
    assert commands==[] and result[0]['outcome']=='not_started'


def test_late_recovery_cannot_overwrite_new_generation(agents,monkeypatch):
    slot=agents.owner_slot(request('a'))
    slot.state={'owner':agents.owner_id(request('a')),'journal_id':'journal','generation':'old','session_id':'sess_one','turn_id':'turn_old','model':'model','outcome':'completed'}
    slot.history=[['old','old answer']]
    job=[]
    def messages(command):
        if command['action']=='inspect':
            job.append(agents.submit_task('new','model',False,True,slot.state,slot.history,request('a')))
            next(job[0])
            yield {'type':'result','outcome':'completed','text':'OLD'}
        else:
            yield {'type':'result','session_id':'sess_one','turn_id':'turn_new','outcome':'completed','text':'NEW'}
    monkeypatch.setattr(agents,'worker_messages',messages)
    result=agents.recover(slot.state,slot.history,request('a'))
    assert result[0]['outcome']=='starting' and result[1][-1][1]==''
    assert '旧操作结果已忽略' in result[2]
    assert list(job[0])[-1][1][-1][1]=='NEW'


def test_real_gradio_build_all_plugin_tabs_and_bindings(tmp_path,monkeypatch):
    monkeypatch.setattr(extensions,'EXTENSIONS_DIR',ROOT/'extensions')
    monkeypatch.setattr(extensions,'STATE_FILE',tmp_path/'state.json')
    extensions.STATE_FILE.write_text('{"version":1,"enabled":{"openai_agents":true}}')
    loaded=extensions.load_extensions(force=True)
    assert all(not item.error for item in loaded)
    with gr.Blocks(analytics_enabled=False) as demo:
        chatbot=gr.Chatbot()
        model=gr.State(SimpleNamespace())
        user_input=gr.Textbox()
        with gr.Tabs(): extensions.render_extension_tabs()
        with gr.Tabs(): extensions.render_extension_settings()
        extensions.render_extension_manager()
        callbacks.invoke('app_ready',AppContext(chatbot,model,user_input))
    assert callbacks.get_errors()==[]
    config=demo.get_config_file()
    names=[component.get('props',{}).get('label') for component in config['components']]
    assert 'Agent 对话' in names and '下载产物' in names
    # Requests are injected and state inputs are real Gradio State components.
    agent_functions=[fn for fn in demo.fns.values() if getattr(fn.fn,'__name__','')=='submit_task'] if isinstance(demo.fns,dict) else [fn for fn in demo.fns if getattr(fn.fn,'__name__','')=='submit_task']
    assert len(agent_functions)==1
    assert agent_functions[0].inputs[-2].__class__ is gr.State
    demo.close()


def test_export_batches_and_notes_isolate_user_data(tmp_path,monkeypatch):
    callbacks.clear_callbacks()
    export=load_plugin('conversation_export')
    path=Path(export.export_conversation([('question','answer')],'JSON'))
    assert json.loads(path.read_text())['messages']==[{'role':'user','content':'question'},{'role':'assistant','content':'answer'}]
    batch=load_plugin('text_batch')
    good=tmp_path/'good.md'; good.write_text('# Heading\n- [ ] Task\n')
    bad=tmp_path/'bad.txt'; bad.write_bytes(b'\xff')
    result=list(batch.analyze_files([str(good),str(bad)]))
    first=json.loads(Path(result[0][1]).read_text())
    second=json.loads(Path(result[1][1]).read_text())
    assert first['processed']==1 and first['results'][0]['tasks']==['Task']
    assert second['processed']==2 and 'error' in second['results'][1]
    notes=load_plugin('auto_notes');monkeypatch.setattr(notes,'DATA_DIR',tmp_path/'notes')
    a,b=SimpleNamespace(),SimpleNamespace()
    notes.set_controls(a,True,'a','')
    ca=ChatContext(a,'a',[],assistant_reply='answer-a')
    cb=ChatContext(b,'b',[],assistant_reply='answer-b')
    notes.append_note(ca);notes.append_note(cb)
    assert 'auto_notes' in ca.metadata and 'auto_notes' not in cb.metadata
    notes.set_controls(b,True,'b','');notes.set_settings(b,'../../outside',True);notes.append_note(cb)
    assert Path(ca.metadata['auto_notes']['path']).parent!=Path(cb.metadata['auto_notes']['path']).parent
    assert tmp_path/'notes' in Path(cb.metadata['auto_notes']['path']).parents


def test_close_at_initial_yield_releases_owner_and_allows_retry(agents,monkeypatch):
    commands=[]
    def messages(command):
        commands.append(command)
        yield {'type':'result','session_id':'sess_retry','turn_id':'turn_retry','outcome':'completed','text':'done'}
    monkeypatch.setattr(agents,'worker_messages',messages)
    first=agents.submit_task('unsent','model',False,True,{},[],request('a'))
    next(first);first.close()
    slot=agents.owner_slot(request('a'))
    assert not slot.running and slot.state['outcome']=='not_started' and slot.history==[]
    result=list(agents.submit_task('retry','model',False,True,{},[],request('a')))[-1]
    assert len(commands)==1 and result[0]['outcome']=='completed'


def test_close_at_followup_initial_yield_restores_previous_turn(agents,monkeypatch):
    state={'owner':agents.owner_id(request('a')),'session_id':'sess_one','turn_id':'turn_old','model':'model','outcome':'completed'}
    monkeypatch.setattr(agents,'worker_messages',lambda command: (_ for _ in ()).throw(AssertionError('must not start')))
    first=agents.submit_task('unsent','model',False,True,state,[['old','answer']],request('a'))
    next(first);first.close()
    slot=agents.owner_slot(request('a'))
    assert not slot.running and slot.state['turn_id']=='turn_old' and slot.state['outcome']=='completed'
    assert slot.history==[['old','answer']]


@pytest.mark.parametrize('name', ['auto_notes','conversation_export','text_batch','openai_agents'])
def test_plugin_english_ui_uses_project_locale(name,monkeypatch):
    callbacks.clear_callbacks()
    module=load_plugin(name)
    monkeypatch.setattr(module,'i18n',SimpleNamespace(language='en_US'))
    with gr.Blocks(analytics_enabled=False) as demo:
        module.render_controls()
    props=[c['props'] for c in demo.get_config_file()['components']]
    labels=[p['label'] for p in props if p.get('label')]
    assert labels and all(not any('\u4e00'<=char<='\u9fff' for char in label) for label in labels)
    if name=='openai_agents':
        assert module.describe({}).startswith('Status: Not started\nProgress:')
    demo.close()
