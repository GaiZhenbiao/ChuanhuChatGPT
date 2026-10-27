"""模型协议与实际本地存储的离线回归测试。"""
from agent_fixtures import *

def test_agent_selection_logs_model_without_explanatory_notice(env, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        model = select(env)
    expected = env.factory.i18n('msg.status.model_set') + ' OpenAI Agent'
    assert expected in [record.getMessage() for record in caplog.records]
    assert not any(env.factory.i18n('model.openai_agent.selection_notice') in record.getMessage()
                   for record in caplog.records)
    assert model.is_hosted_agent

def test_main_factory_send_artifact_followup(env,monkeypatch):
    calls,file=complete(env,monkeypatch,True);model=select(env)
    output=send(env,model)
    assert output[-1][0]==[['hello','Agent synthetic answer']]
    assert model._artifacts[0]['path']==str(file)
    assert not any(isinstance(row[1],tuple) for row in model.chatbot)
    send(env,model,'continue')
    runs=[c for c in calls if c['action']=='run']
    assert runs[0]['session_id'] is None and runs[1]['session_id']=='sess_test'
    assert runs[1]['prompt']=='continue' and runs[1]['history_reference'] is None
    assert model.api_key is None


def test_first_yield_close_leaves_accepted_background_task_running(env, monkeypatch):
    complete(env, monkeypatch)
    model=select(env);generator=env.wrappers['predict'](model,'hello',[],request=request())
    next(generator);generator.close()
    model._background_task.thread.join(3)
    assert not model._background_task.thread.is_alive()
    assert model.history[-1]['content']=='Agent synthetic answer'
    assert model._state['outcome']=='completed' and not model._running


def test_stop_before_worker_rolls_back(env):
    model=select(env);generator=model.predict('hello',[])
    next(generator);model.interrupt();list(generator)
    assert model.history==[] and model._state['outcome']=='not_started'


def test_cancel_waits_for_current_turn_not_previous(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    calls=[];ready=threading.Event();release=threading.Event()
    def worker(command):
        calls.append(deepcopy(command))
        if command['action']=='run':
            ready.set();assert release.wait(3)
            yield dict(type='progress',session_id='sess_test',turn_id='turn_new',outcome='in_progress')
            yield dict(type='result',session_id='sess_test',turn_id='turn_new',outcome='cancelled')
        elif command['action']=='cancel':
            assert command['turn_id']=='turn_new'
            yield dict(type='result',outcome='cancel_requested')
        elif command['action']=='download': yield dict(type='result',artifacts=[])
        else:raise AssertionError(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    thread=threading.Thread(target=lambda:send(env,model,'second'));thread.start()
    assert ready.wait(3);model.interrupt();assert [c['action'] for c in calls]==['run']
    release.set();thread.join(3)
    assert not thread.is_alive() and model._state['outcome']=='cancelled'
    assert [c['action'] for c in calls]==['run','cancel','download']
    complete(env,monkeypatch);send(env,model,'after stop')


@pytest.mark.parametrize('known',[True,False])
def test_uncertain_send_blocks_duplicates_and_reconnect_never_resubmits(env,monkeypatch,known):
    calls=[]
    def worker(command):
        calls.append(command)
        if command['action']=='run' and known: yield dict(type='progress',session_id='sess_test',turn_id='turn_one',outcome='in_progress',text='partial')
        elif command['action'] in ('recover','recover_unknown'): yield dict(type='result',session_id='sess_test',turn_id='turn_one',outcome='cancelled',text='recovered')
        elif command['action']=='download':yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker);model=select(env);send(env,model)
    assert model._state['outcome']==('incomplete' if known else 'uncertain')
    with pytest.raises(gr.Error):send(env,model,'duplicate')
    with pytest.raises(gr.Error):list(model.retry(model.chatbot))
    list(model.reconnect())
    settle_files(model)  # File discovery is asynchronous after the main result.
    assert [c['action'] for c in calls]==['run','recover' if known else 'recover_unknown','download']
    assert model._state['outcome']=='cancelled'


def test_no_input_or_output_application_caps(env,monkeypatch):
    long='长'*150001
    def worker(command):
        if command['action']=='run':
            assert command['prompt']==long
            yield dict(type='result',session_id='sess_test',turn_id='turn_one',outcome='completed',text=long)
        elif command['action']=='download':yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker);model=select(env);send(env,model,long)
    assert model.history[-1]['content']==long


def test_model_effort_update_rolls_back_on_error_and_keeps_session(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env);send(env,model)
    count=len(calls)
    model.set_agent_model('gpt-6-sol','high')
    assert len(calls)==count and model.model_name!='gpt-6-sol'
    send(env,model,'apply on send')
    assert model.model_name=='gpt-6-sol' and model._reasoning=='high' and model._state['session_id']=='sess_test'
    assert [c['action'] for c in calls[count:]]==['update','run','download']
    before=list(model.history)
    monkeypatch.setattr(env.agents,'worker_messages',lambda c:iter([dict(type='error',message='rejected',diagnostics={'status_code':400})]))
    model.set_agent_model('invalid-model','low')
    output=send(env,model,'not sent')
    assert '消息未发送' in output[-1][1] and model.history==before
    assert model.model_name=='gpt-6-sol' and model._reasoning=='high'
    assert model.agent_model_choice==('invalid-model','low') and not model._needs_sync


def test_update_eof_not_success(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    old=(model.model_name,model._reasoning)
    monkeypatch.setattr(env.agents,'worker_messages',lambda c:iter([]))
    model.set_agent_model('gpt-6-sol','high')
    output=send(env,model,'not sent')
    assert '消息未发送' in output[-1][1] and model._needs_sync
    assert (model.model_name,model._reasoning)==old


def test_dropdown_changes_collapse_to_one_update_and_skip_unchanged_values(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env);send(env,model)
    offset=len(calls)
    model.set_agent_model('gpt-6-sol','default')
    model.set_agent_model('gpt-6-sol','high')
    model.set_agent_model('gpt-6.1-sol','medium')
    assert len(calls)==offset
    send(env,model,'latest choice')
    assert [c['action'] for c in calls[offset:]]==['update','run','download']
    assert calls[offset]['model']=='gpt-6.1-sol' and calls[offset]['reasoning']=='medium'
    offset=len(calls);model.set_agent_model('gpt-6.1-sol','medium');send(env,model,'same choice')
    assert [c['action'] for c in calls[offset:]]==['run','download']


def test_new_session_choice_does_not_issue_separate_update(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env)
    model.set_agent_model('gpt-6-sol','high');assert not calls
    send(env,model)
    assert [c['action'] for c in calls]==['run','download']
    assert calls[0]['model']=='gpt-6-sol' and calls[0]['reasoning']=='high'


def test_stop_during_parameter_update_never_submits_or_cancels_previous_turn(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    previous=list(model.history);old_turn=model._state['turn_id']
    entered=threading.Event();release=threading.Event();calls=[]
    def worker(command):
        calls.append(command['action'])
        assert command['action']=='update'
        entered.set();assert release.wait(3)
        yield {'type':'result','settings':{'model':'gpt-6-sol','reasoning':'high'}}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model.set_agent_model('gpt-6-sol','high')
    thread=threading.Thread(target=lambda:send(env,model,'cancel this send'));thread.start()
    assert entered.wait(3);model.interrupt();release.set();thread.join(3)
    assert not thread.is_alive() and calls==['update']
    assert model.history==previous and model._state['turn_id']==old_turn
    assert model.model_name=='gpt-6-sol' and '尚未发送' in model._notice


def test_queued_send_freezes_next_model_choice(env,monkeypatch):
    from modules.model_capabilities import reserve_submission
    complete(env,monkeypatch);model=select(env)
    model.set_agent_model('gpt-6-sol','high')
    envelope=reserve_submission(model,'fixed choice')
    with pytest.raises(gr.Error):model.set_agent_model('gpt-6.1-sol','low')
    list(env.wrappers['predict'](model,envelope,[],request=request()))
    assert model.model_name=='gpt-6-sol'


def test_session_config_is_locked_until_a_new_conversation(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env)
    generator=model.predict('first',[]);next(generator)
    value=dict(model._tool_settings,network=False,web_search=False)
    with pytest.raises(gr.Error):model.save_agent_tools(value)
    with pytest.raises(gr.Error):model.set_agent_model('gpt-6-sol','high')
    list(generator)
    assert model._session_settings['tools']['network'] is True
    send(env,model,'original session')
    assert [c for c in calls if c['action']=='run'][-1]['tool_settings']['network'] is True
    old_path=model.history_file_path;model.new_session_from_history();model.save_agent_tools(value);send(env,model,'new config')
    latest=[c for c in calls if c['action']=='run'][-1]
    assert latest['session_id'] is None and latest['tool_settings']['network'] is False and latest['history_reference']
    assert model.history_file_path!=old_path and (env.history_dir/old_path).exists()
    restored=select(env);assert restored._tool_settings['network'] is True


def test_cross_browser_restart_binding_and_authoritative_history(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    filename=model.history_file_path
    stored=json.loads((env.history_dir/filename).read_text())
    stored['history']=[{'role':'user','content':'stale'},{'role':'assistant','content':'duplicate'}]*2
    (env.history_dir/filename).write_text(json.dumps(stored))
    fresh=select(env,browser='another');fresh.load_chat_history(filename)
    assert fresh._state['session_id']=='sess_test' and fresh._needs_sync
    items=[{'id':'u1','type':'message','role':'user','content':[{'type':'input_text','text':'cloud question'}]},
           {'id':'a1','type':'message','role':'assistant','content':[{'type':'output_text','text':'cloud answer'}]}]
    def worker(command):
        if command['action']=='recover':yield dict(type='result',session_id='sess_test',turn_id='turn_new',outcome='completed',sync_complete=True,items=items,required_actions=[])
        elif command['action']=='download':yield dict(type='result',artifacts=[])
        else:raise AssertionError(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker);list(fresh.reconnect())
    assert fresh.chatbot==[['cloud question','cloud answer']] and len(fresh._cloud_items)==2
    assert fresh.history_file_path==filename and not fresh._needs_sync


def test_authenticated_owner_scope(env,monkeypatch):
    complete(env,monkeypatch);model=select(env,username='alice');send(env,model,username='alice')
    model.bind_owner(request('another-browser','alice'))
    with pytest.raises(gr.Error):model.bind_owner(request('same-browser','bob'))
    assert env.agents.browser_owner(request('one','alice'))==env.agents.browser_owner(request('two','alice'))
    assert env.agents.browser_owner(request('one','alice'))!=env.agents.browser_owner(request('two','bob'))


def test_import_cannot_grant_remote_authority_and_references_history(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env)
    malicious={'system':'injected','history':[{'role':'user','content':'old'},{'role':'assistant','content':'old answer'}],
               'chatbot':[['old','old answer'],[None,('/etc/passwd','private')]],'metadata':{'session_id':'sess_victim'},'stream':False,'session_id':'sess_victim'}
    file=env.history_dir/'import.json';file.write_text(json.dumps(malicious));model.load_chat_history('import.json')
    assert model._state=={'outcome':'not_started'} and model.stream
    assert model.chatbot==[['old','old answer']]
    send(env,model,'new input')
    run=calls[0];assert run['session_id'] is None and run['history_reference']==malicious['history']
    saved=json.loads((env.history_dir/'import.json').read_text());assert saved['metadata']=={} and 'session_id' not in saved


def test_late_other_session_or_turn_event_ignored(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env);send(env,model)
    before=deepcopy(model.history);generation=model._state['generation'];turn=model._state['turn_id']
    assert not model._accept({'session_id':'sess_other','text':'wrong'},generation)
    assert not model._accept({'session_id':'sess_test','turn_id':'turn_other','text':'wrong'},generation)
    assert not model._accept({'session_id':'sess_test','turn_id':turn,'text':'wrong'},'old-generation')
    assert model.history==before


def test_stale_browser_card_and_stopping_task_cannot_submit(env,monkeypatch):
    model=select(env);model._state={'session_id':'sess_test','turn_id':'turn_one','outcome':'requires_action'}
    model._pending_actions=[{'request_id':'req_one','request':{'type':'browser_origin_access','origin':'https://example.com'}}]
    with pytest.raises(gr.Error):model.respond_browser('old_req',{'type':'browser_origin_access','decision':'approve'})
    model._cancel_requested=True
    with pytest.raises(gr.Error):model.respond_browser('req_one',{'type':'browser_origin_access','decision':'approve'})


def test_journal_server_private_not_exported(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    db=Path(env.agents.shared.chuanhu_path)/'agent_data/bindings.sqlite3'
    assert db.exists() and db.stat().st_mode & 0o777==0o600
    text=(env.history_dir/model.history_file_path).read_text()
    assert 'sess_test' not in text and 'offline-fixture-only' not in text
    assert 'offline-fixture-only' not in repr(model._store().get(model._owner,model.history_file_path))


def test_gradio_request_injection(env):
    from gradio.helpers import special_args
    browser=gr.Request(session_hash='native-browser')
    args,_,_=special_args(env.wrappers['predict'],[None,'text',[],False,None,'English'],request=browser)
    assert args[-1] is browser


def test_stop_during_download_does_not_cancel_completed_turn(env,monkeypatch):
    model=select(env);calls=[]
    def worker(command):
        calls.append(command)
        if command['action']=='run':yield dict(type='result',session_id='sess_test',turn_id='turn_one',outcome='completed',text='done')
        elif command['action']=='download':model.interrupt();yield dict(type='result',artifacts=[])
        else:raise AssertionError(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker);send(env,model)
    assert model._state['outcome']=='completed' and [c['action'] for c in calls]==['run','download']


def test_failed_recovery_preserves_display_and_keeps_send_blocked(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model);before=deepcopy(model.chatbot)
    model._needs_sync=True
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([dict(type='error',outcome='not_started',message='offline')]))
    list(model.reconnect());assert model.chatbot==before and model._needs_sync
    with pytest.raises(gr.Error):send(env,model,'duplicate')
def test_ordinary_partial_switch_rejected_then_complete_history_roundtrip(env,monkeypatch):
    complete(env,monkeypatch)
    ordinary=select(env,name='GPT3.5 Turbo')
    def stream():
        yield 'ordinary partial'
        yield 'ordinary completed'
    ordinary.get_answer_stream_iter=stream
    generator=ordinary.predict('ordinary task',[])
    next(generator);next(generator);partial=next(generator)
    assert partial[0][-1][1]=='ordinary partial'
    assert ordinary.history==[{'role':'user','content':'ordinary task'}]
    switched=env.factory.change_model('OpenAI Agent',None,None,None,None,None,'',ordinary,request())
    assert switched[0] is ordinary and switched[8]['value']=='GPT3.5 Turbo'
    assert ordinary._chat_running and not ordinary._chat_retired
    list(generator)
    assert ordinary.history[-1]=={'role':'assistant','content':'ordinary completed'}
    agent=select(env,ordinary);send(env,agent,'agent task')
    expected=[{'role':'user','content':'ordinary task'},{'role':'assistant','content':'ordinary completed'},
              {'role':'user','content':'agent task'},{'role':'assistant','content':'Agent synthetic answer'}]
    assert agent.history==expected
    saved=json.loads((env.history_dir/agent.history_file_path).read_text())
    assert saved['history']==expected
    assert saved['chatbot']==[['ordinary task','ordinary completed'],['agent task','Agent synthetic answer']]
    agent.load_chat_history(agent.history_file_path)
    assert agent.history==expected and agent.chatbot==saved['chatbot']
    imported=select(env,browser='browser-two');imported.load_chat_history(agent.history_file_path)
    assert imported.history==expected and imported._state['session_id']=='sess_test' and imported._needs_sync


@pytest.mark.parametrize('close_at',[0,2])
def test_closed_ordinary_iterator_restores_complete_history_before_switch(env,monkeypatch,close_at):
    complete(env,monkeypatch);ordinary=select(env,name='GPT3.5 Turbo')
    send(env,ordinary,'completed task');previous=deepcopy(ordinary.history);display=deepcopy(ordinary.chatbot)
    generator=ordinary.predict('interrupted task',deepcopy(display))
    for _ in range(close_at+1):next(generator)
    generator.close()
    assert ordinary.history==previous and ordinary.chatbot==display and not ordinary._chat_running
    agent=select(env,ordinary);assert agent.history==previous
    send(env,agent,'agent task')
    agent.load_chat_history(agent.history_file_path)
    assert agent.history[-1]['content']=='Agent synthetic answer' and len(agent.history)==4


def test_ordinary_switch_atomic_rejects_queued_old_predict(env,monkeypatch):
    ordinary=select(env,name='GPT3.5 Turbo');send(env,ordinary)
    constructor=env.agents.OpenAIAgentsClient
    ready=threading.Event();release=threading.Event();errors=[];switched=[]
    def blocked(*a,**k):
        ready.set();assert release.wait(3);return constructor(*a,**k)
    monkeypatch.setattr(env.agents,'OpenAIAgentsClient',blocked)
    switch=threading.Thread(target=lambda:switched.append(select(env,ordinary)))
    switch.start();assert ready.wait(3)
    def queued():
        try:list(ordinary.predict('late ordinary task',ordinary.chatbot))
        except gr.Error as error:errors.append(error)
    old_predict=threading.Thread(target=queued);old_predict.start();release.set()
    switch.join(3);old_predict.join(3)
    assert not switch.is_alive() and not old_predict.is_alive()
    assert errors and switched[0] is not ordinary and ordinary._chat_retired
    assert switched[0].history==ordinary.history and len(ordinary.history)==2


def test_ordinary_stop_keeps_partial_pair_and_can_switch(env,monkeypatch):
    complete(env,monkeypatch);ordinary=select(env,name='GPT3.5 Turbo')
    def stream():
        yield 'ordinary partial'
        yield 'ordinary completed'
    ordinary.get_answer_stream_iter=stream
    generator=ordinary.predict('ordinary task',[])
    next(generator);next(generator);next(generator)
    ordinary.interrupt();list(generator)
    assert ordinary.history[-1]['content']=='ordinary partial' and not ordinary._chat_running
    agent=select(env,ordinary);send(env,agent,'agent task')
    agent.load_chat_history(agent.history_file_path)
    assert len(agent.history)==4 and agent.history[-1]['content']=='Agent synthetic answer'


def test_ordinary_retry_reserves_before_rewind_and_close_restores_history(env,monkeypatch):
    complete(env,monkeypatch);ordinary=select(env,name='GPT3.5 Turbo');send(env,ordinary)
    previous=deepcopy(ordinary.history)
    generator=ordinary.retry(deepcopy(ordinary.chatbot));next(generator)
    assert ordinary._chat_running
    assert select(env,ordinary) is ordinary
    generator.close()
    assert ordinary.history==previous and not ordinary._chat_running
    ordinary.get_answer_stream_iter=lambda:iter(['ordinary regenerated'])
    list(ordinary.retry(deepcopy(ordinary.chatbot)))
    assert len(ordinary.history)==2 and ordinary.history[-1]['content']=='ordinary regenerated'


def test_failed_explicit_fork_returns_original_session(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model)
    original=(model.history_file_path,deepcopy(model.chatbot),model._state['session_id'])
    model.new_session_from_history();model.save_agent_tools(dict(model._tool_settings,network=False))
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([dict(type='error',outcome='not_started',message='unsupported API')]))
    send(env,model,'new attempted request')
    assert (model.history_file_path,model.chatbot,model._state['session_id'])==original
    assert model._tool_settings['network'] is True and '已回到原会话' in model._notice
    assert len(list(env.history_dir.glob('*.json')))==2


def test_cross_browser_double_send_reservation(env,monkeypatch):
    complete(env,monkeypatch);one=select(env);send(env,one)
    two=select(env,browser='two');two.history_file_path=one.history_file_path;two._state=deepcopy(one._state)
    two.history=deepcopy(one.history);two.chatbot=deepcopy(one.chatbot);two._display=deepcopy(one._display);two._session_settings=deepcopy(one._session_settings)
    generator=one.predict('pending',one.chatbot);next(generator)
    with pytest.raises(gr.Error):list(two.predict('duplicate',two.chatbot))
    generator.close()


def test_summary_title_keeps_binding_and_uses_existing_choice(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env);send(env,model)
    old_worker=env.agents.worker_messages
    def worker(command):
        if command['action']=='title':yield dict(type='result',title='简洁标题')
        else:yield from old_worker(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    model.auto_name_chat_history(env.locale('naming.by_model_summary'),'hello',False)
    assert model.history_file_path=='简洁标题.json'
    assert model._store().get(model._owner,model.history_file_path)['state']['session_id']=='sess_test'


def test_terminal_history_sync_failure_preserves_answer_and_blocks_send(env,monkeypatch):
    def worker(command):
        if command['action']=='run':yield dict(type='result',session_id='sess_test',turn_id='turn_one',outcome='completed',text='answer',sync_complete=False,items=[])
        elif command['action']=='download':yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker);model=select(env);send(env,model)
    assert model._needs_sync and model.chatbot[-1][1]=='answer' and '尚未完整同步' in model._notice
    with pytest.raises(gr.Error):model._assert_idle()


def test_recovered_live_delta_updates_before_item_done(env):
    from modules.agent.runtime import TurnState,_seed
    model=select(env);model._state={'generation':'g','session_id':'sess_test','turn_id':'t1','outcome':'in_progress'}
    model._session_settings=model._current_settings()
    state=TurnState('sess_test','t1')
    _seed(state,{'turn_id':'t1','outcome':'in_progress','items':[
        {'id':'u','type':'message','role':'user','turn_id':'t1','status':'completed','content':[{'type':'input_text','text':'question'}]},
        {'id':'a','type':'message','role':'assistant','turn_id':'t1','status':'in_progress','content':[{'type':'output_text','text':'first '}]}],
        'required_actions':[],'settings':{}})
    model._accept(state.snapshot(),'g',restoring=True)
    state.accept({'type':'agent.session.turn.output_text.delta','session_id':'sess_test','turn_id':'t1','item_id':'a','output_index':0,'content_index':0,'delta':'new text'})
    model._accept(state.snapshot(),'g',restoring=True)
    assert model.history[-1]['content']=='first new text' and state.sync_complete is None


def test_recovery_does_not_apply_previous_stop_to_a_new_turn(env):
    model=select(env);model._state={'generation':'g','session_id':'sess_test','turn_id':'old_turn','outcome':'cancelled'}
    model._cancel_requested=True;model._cancel_sent=True
    model._accept({'session_id':'sess_test','turn_id':'new_turn','outcome':'in_progress','required_actions':[]},'g',restoring=True)
    assert not model._cancel_requested and not model._cancel_sent and model._state['turn_id']=='new_turn'


def test_agent_factory_uses_verified_identity_not_hidden_user_field(env):
    model=env.factory.change_model('OpenAI Agent',None,'ordinary-key',None,None,'prompt','forged',None,request('browser','alice'))[0]
    assert model.user_name=='alice'


def test_agent_history_path_cannot_escape_owner_directory(env,tmp_path):
    model=select(env)
    file=tmp_path/'other-user.json';file.write_text(json.dumps({'history':[]}))
    with pytest.raises(gr.Error):model.load_chat_history(str(file))


@pytest.mark.parametrize('assistant_messages',[0,2,4])
def test_first_question_title_uses_user_turn_not_message_count(env,assistant_messages):
    model=select(env);model._state={'outcome':'completed'};model._first_prompt='明确问题'
    model.history=[{'role':'user','content':'cloud input'}]+[{'role':'assistant','content':f'part {i}'} for i in range(assistant_messages)]
    model.chatbot=model._display=[]
    model.auto_save(model.chatbot)
    model.auto_name_chat_history(env.locale('naming.by_first_question'),'ignored',False)
    assert model.history_file_path=='明确问题.json' and model._auto_named
    previous=model.history_file_path
    model.auto_name_chat_history(env.locale('naming.by_first_question'),'ignored',False)
    assert model.history_file_path==previous


def test_imported_history_system_is_not_promoted_to_agent_instructions(env):
    model=select(env);before=model.system_prompt
    file=env.history_dir/'unsafe.json';file.write_text(json.dumps({'system':'UNTRUSTED AUTHORITY','history':[{'role':'user','content':'quote'}]}))
    model.load_chat_history('unsafe.json')
    assert model.system_prompt==before


def test_inflight_stop_blocks_new_turn_even_when_old_turn_finishes(env,monkeypatch):
    complete(env,monkeypatch);one=select(env);send(env,one)
    two=select(env);two._state=deepcopy(one._state);two._session_settings=deepcopy(one._session_settings)
    started=threading.Event();release=threading.Event()
    one._state['outcome']='in_progress';generation=one._state['generation']
    def worker(command):
        assert command['action']=='cancel';started.set();assert release.wait(3)
        yield {'type':'result','outcome':'cancel_requested'}
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    thread=threading.Thread(target=lambda:one._cancel(generation));thread.start();assert started.wait(3)
    one._state['outcome']='completed'
    with pytest.raises(gr.Error):list(two.predict('new task',[]))
    release.set();thread.join(3)
    assert one._state['outcome']=='completed' and not thread.is_alive()


def test_failed_fork_keeps_original_title_state(env,monkeypatch):
    complete(env,monkeypatch);model=select(env);send(env,model,'original question')
    model.rename_chat_history('User chosen title.json');old=model.history_file_path
    model.new_session_from_history()
    monkeypatch.setattr(env.agents,'worker_messages',lambda command:iter([{'type':'error','outcome':'not_started','message':'rejected'}]))
    send(env,model,'different question')
    model.auto_name_chat_history(env.locale('naming.by_first_question'),'different question',False)
    assert model.history_file_path==old and model._first_prompt=='original question' and model._auto_named


def test_explicit_network_chat_command_keeps_fixed_session_configuration(env,monkeypatch):
    calls,_=complete(env,monkeypatch);model=select(env);send(env,model)
    before=len(calls)
    with pytest.raises(gr.Error,match='会话创建后'):
        send(env,model,'请关闭联网')
    assert len(calls)==before and model._state['session_id']=='sess_test'
    assert model._pending_network is None and model._session_settings['tools']['network'] is True
    assert '已固定' in model._notice
    model.new_session_from_history();model.save_agent_tools(dict(model._tool_settings,network=False));send(env,model,'continue task')
    command=[c for c in calls if c['action']=='run'][-1]
    assert command['session_id'] is None and command['tool_settings']['network'] is False
    assert command['tool_settings']['web_search'] is True


def test_active_agent_copy_matches_current_connection_and_recovery_contract(env):
    for language in ('zh_CN','en_US'):
        values=json.loads((ROOT/'locale'/f'{language}.json').read_text())['model']['openai_agent']
        assert set(values)=={'description','slogan','selection_notice','invalid_response'}
        assert not any(old in ' '.join(values.values()) for old in ('隔离 SDK','专用密钥','只读对账','计费','isolated SDK','dedicated credentials','billed','Regenerate'))


def test_model_specific_api_key_retains_existing_metadata_priority(env):
    env.presets.MODEL_METADATA['OpenAI Agent']['api_key']='synthetic-model-scoped-key'
    model=select(env)
    assert model._connection_key=='synthetic-model-scoped-key'
