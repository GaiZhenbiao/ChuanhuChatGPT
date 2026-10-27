"""Known file metadata is published with terminal text, before byte completion."""
from copy import deepcopy
from io import StringIO
import json
from threading import Event, Thread
import pytest
from agent_fixtures import env, select, request
from test_finalization_boundary import complete_state, wait_main, wait_files
from modules.agent.artifacts import ArtifactObserver, preparing_artifacts
from modules.agent.ui import ArtifactPanel


def metadata(**extra):
    return dict(id='file-known',session_id='sess_one',turn_id='turn_one',
                filename='report.txt',path='/workspace/report.txt',size_bytes=12,**extra)


@pytest.mark.parametrize('field',['artifact_metadata','transcript_artifacts'])
def test_first_terminal_task_snapshot_already_contains_preparing_card_without_waiting_bytes(env,monkeypatch,field):
    from modules.agent.tasks import BackgroundTask
    published=[];entered,release=Event(),Event()
    original=BackgroundTask.publish
    def publish(self):
        original(self)
        if self.snapshot:published.append(deepcopy(self.snapshot[0]))
    monkeypatch.setattr(BackgroundTask,'publish',publish)
    def worker(command):
        if command['action']=='run':
            state=complete_state();state.submission_started=True
            payload=state.snapshot();payload[field]=[metadata()]
            yield dict(type='result',**payload)
        elif command['action']=='download':
            entered.set();assert release.wait(5)
            yield dict(type='result',artifacts=[])
        else:raise AssertionError(command['action'])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model=select(env);stream=env.wrappers['predict'](model,'question',[],request=request());next(stream)
    try:
        task=wait_main(model);assert entered.wait(3)
        terminal=next(frame for frame in published if frame['_state'].get('outcome')=='completed')
        assert terminal['_display'][-1][1]=='answer'
        assert terminal['_artifacts'][0]['id']=='file-known'
        assert terminal['_artifacts'][0]['status']=='preparing'
        assert 'path' not in terminal['_artifacts'][0]
        assert not release.is_set();model._assert_idle()
        # The immutable same-frame projection drives both outputs; no refresh
        # callback or second source can supply this card during the assertion.
        view=model.new_view();task.project(view)
        monkeypatch.setattr(view,'refresh_files',lambda **kwargs:None)
        markup=ArtifactPanel.values(view)[1]['value']
        assert 'report.txt' in markup and '准备中' in markup
        assert 'disabled="disabled"' in markup and 'data-file-action=""' in markup
        assert 'data-file-action="download"' not in markup
        assert view._display[-1][1]=='answer'
    finally:
        release.set();wait_files(model);stream.close()


@pytest.mark.parametrize('records',[[],[{'id':'unknown'}],
    [dict(metadata(),session_id='sess_other')],[dict(metadata(),turn_id='turn_other')]])
def test_no_card_is_invented_without_named_current_turn_metadata(env,records):
    model=select(env);model._state.update(generation='g',session_id='sess_one',turn_id='turn_one')
    assert model._accept(dict(type='result',session_id='sess_one',turn_id='turn_one',outcome='completed',text='answer',artifact_metadata=records),'g')
    assert not model._artifacts


def test_provider_path_and_status_can_never_enable_download():
    records=preparing_artifacts([dict(metadata(),status='ready',size_bytes=-1)],session_id='sess_one',turn_id='turn_one')
    assert records[0]['status']=='preparing' and 'path' not in records[0]
    assert records[0]['remote_path']=='/workspace/report.txt' and records[0]['size'] is None


def test_late_old_turn_or_retired_generation_metadata_cannot_repopulate_current_model(env):
    model=select(env);model._state.update(generation='new',session_id='sess_one',turn_id='turn_two')
    message=dict(type='result',session_id='sess_one',turn_id='turn_one',outcome='completed',text='old',artifact_metadata=[metadata()])
    assert not model._accept(message,'old')
    assert not model._accept(message,'new')
    assert not model._artifacts and model._state['turn_id']=='turn_two'
    model._local_history_deleted=lambda:True
    message.update(turn_id='turn_two',artifact_metadata=[dict(metadata(),turn_id='turn_two')])
    assert not model._accept(message,'new') and not model._artifacts


def test_observer_snapshot_retains_metadata_before_blocked_emit_and_is_scoped():
    entered,release=Event(),Event()
    def emit(*args,**kwargs):entered.set();assert release.wait(3)
    observer=ArtifactObserver(object(),emit);observer.session_id='sess_one';observer.turn_id='turn_one'
    record=preparing_artifacts([metadata()],session_id='sess_one',turn_id='turn_one')[0]
    publish=Thread(target=observer._publish,args=([record],));publish.start();assert entered.wait(2)
    try:
        snapshot=observer.snapshot('sess_one','turn_one')
        assert snapshot==[record] and not release.is_set()
        snapshot[0]['name']='changed';assert observer.snapshot('sess_one','turn_one')[0]['name']=='report.txt'
        assert observer.snapshot('sess_other','turn_one')==[] and observer.snapshot('sess_one','turn_two')==[]
    finally:release.set();publish.join(3)


def test_real_worker_terminal_result_includes_observer_metadata_before_late_progress(monkeypatch):
    from modules.agent import artifacts, worker
    entered,release=Event(),Event();instances=[];frames=[];threads=[]
    class Observed(ArtifactObserver):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);instances.append(self)
    monkeypatch.setattr(artifacts,'ArtifactObserver',Observed)
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(worker,'create_client',lambda connection:Client())
    def emit(kind,**frame):
        if kind=='progress':entered.set();assert release.wait(3)
        frames.append(dict(type=kind,**frame))
        if kind=='result':
            assert not release.is_set();release.set()
    monkeypatch.setattr(worker,'emit',emit)
    def run(*args,on_progress,**kwargs):
        state=complete_state();observer=instances[0]
        observer.session_id,observer.turn_id=state.session_id,state.turn_id
        record=preparing_artifacts([metadata()],session_id=state.session_id,turn_id=state.turn_id)[0]
        thread=Thread(target=observer._publish,args=([record],));threads.append(thread);thread.start()
        assert entered.wait(2);on_progress(state);return state
    monkeypatch.setattr(worker,'run_task',run)
    monkeypatch.setattr(worker.sys,'stdin',StringIO(json.dumps({'action':'run','prompt':'offline','model':'synthetic'})))
    try:worker.main()
    finally:
        release.set()
        for thread in threads:thread.join(3)
    terminal=next(frame for frame in frames if frame['type']=='result')
    assert terminal['text']=='answer' and terminal['artifacts'][0]['status']=='preparing'
    assert frames[0]['type']=='result','terminal does not wait for the observer progress emission'


def test_real_gradio_preparing_card_arrives_no_later_than_terminal_body(env,monkeypatch):
    import asyncio
    import gradio as gr
    from gradio.state_holder import SessionState
    from modules.agent.message_files import decode_rows
    from modules.agent.ui import AgentPanel
    from modules.model_capabilities import CapabilityUI
    release=Event()
    def worker(command):
        if command['action']=='run':
            payload=complete_state().snapshot();payload['transcript_artifacts']=[metadata()]
            yield dict(type='result',**payload)
        else:
            assert release.wait(10)
            yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model=select(env)
    with gr.Blocks(analytics_enabled=False) as app:
        current=gr.State();prompt=gr.Textbox();chat=gr.Chatbot();status=gr.Markdown()
        send=gr.Button();stop=gr.Button();selector=gr.Dropdown();marker=gr.HTML()
        caps=CapabilityUI([],selector,marker,send,stop);caps.wire(current,chat)
        panel=AgentPanel();panel.selectors();panel.output_components();panel.settings_components()
        outputs=[chat,status,*panel.outputs,*caps.outputs]
        send.click(panel.wrap_predict(env.wrappers['predict'],caps),[current,prompt,chat],outputs)
    state=SessionState(app);state[current._id]=model
    index=next(i for i,fn in enumerate(app.fns) if fn.fn and fn.fn.__name__=='predict_with_ui')
    card_index=outputs.index(panel.artifacts.list)
    async def exercise():
        result=await app.process_api(index,[None,'question',[]],state=state,request=request())
        found=False;visible_card=''
        while True:
            card=result['data'][card_index]
            markup=card.get('value') if isinstance(card,dict) else card
            if markup is not None:visible_card=markup
            frame=result['data'][0]
            rows=frame.get('value') if isinstance(frame,dict) else frame
            if rows and any(row[1]=='answer' for row in decode_rows(rows,model._conversation_id)) and not found:
                found=True
                # FrameUpdates may have delivered a fast card in the preceding
                # controls frame; unchanged fields are valid Gradio no-ops.
                assert 'report.txt' in visible_card and 'disabled="disabled"' in visible_card
                assert 'data-file-action="download"' not in visible_card
                assert not release.is_set()
            if not result['is_generating']:break
            result=await app.process_api(index,[None,'question',[]],state=state,request=request(),iterator=result['iterator'])
        assert found and not release.is_set()
        assert state.blocks_config.blocks[send._id].interactive
        model._assert_idle()
    try:asyncio.run(exercise())
    finally:release.set();wait_files(model);app.close()
