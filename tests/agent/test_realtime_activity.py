"""Actual SDK event shapes, offline clocks and reversible chronological UI."""
from copy import deepcopy
import html
import json
import re
import pytest
from agent_fixtures import env, select
from test_runtime import event, turn, message, FakeClient
from modules.agent import runtime, transcript
from modules.agent.activity import ActivityClock
from modules.agent.transcript_view import i18n
from modules.agent.message_files import decode_rows
from modules.agent.ui import AgentPanel


def item_event(item, index, suffix='added', **extra):
    return event('item.'+suffix,item=item,output_index=index,**extra)


def reasoning(status='in_progress',text=''):
    return dict(id='r',type='reasoning',turn_id='t1',status=status,
                summary=[dict(type='summary_text',text=text)],encrypted_content='HIDDEN',content='PRIVATE')


def model_for_stream(env):
    model=select(env);model._state.update(generation='g',session_id='sess_test',turn_id='t1',outcome='in_progress')
    model.history=[dict(role='user',content='question'),dict(role='assistant',content='')]
    model._display=model.chatbot=[['question','']];model._answer_index=1;model._answer_row=0;model._running=True
    return model


def accept(model,state):
    model._accept(dict(type='progress',**state.snapshot()),'g')


def rendered(model):
    def formatter(value):
        return '<div class="raw-message hideM">'+html.escape(value)+'</div><div class="md-message">'+html.escape(value)+'</div>'
    return AgentPanel(format_assistant=formatter).render_chat(model,model._display)


def test_public_summary_and_tools_visible_before_final_with_commentary_order_and_exact_copy(env):
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(message('u','question',role='user'),None))
    state.accept(item_event(reasoning(),0))
    delta=event('reasoning_summary_text.delta',item_id='r',output_index=0,summary_index=0,delta='Check weather',event_id='public-delta')
    state.accept(delta);state.accept(delta)
    state.accept(event('reasoning_summary_text.done',item_id='r',output_index=0,summary_index=0,text='Check weather.'))
    state.accept(item_event(reasoning('completed','Check weather.'),0,'done'))
    model=model_for_stream(env);accept(model,state)
    early=rendered(model);early_html=str(early)
    assert 'Check weather.' in early_html and i18n('ui.agent_activity.thinking_completed') in early_html
    assert 'HIDDEN' not in early_html and 'PRIVATE' not in early_html
    state.accept(item_event(dict(message('comment','I will check'),phase='commentary'),1))
    tool=dict(id='web',type='web_search_call',turn_id='t1',status='in_progress',action=dict(type='search',query='weather'))
    state.accept(item_event(tool,2));accept(model,state)
    middle=rendered(model);middle_html=str(middle)
    assert middle_html.index('Check weather.')<middle_html.index('md-message">I will check')<middle_html.index('网页搜索')
    assert 'aria-label="网页搜索 · 进行中"' in middle_html and 'data-running="true"' in middle_html
    assert decode_rows(middle,model._conversation_id)==model._display
    state.accept(item_event(dict(tool,status='completed'),2,'done'))
    state.accept(item_event(dict(message('answer','Final weather'),phase='final_answer'),3,'done'))
    state.accept(turn('completed'));accept(model,state)
    final=rendered(model);body=final[0][1]
    assert body.index('Check weather.')<body.index('md-message">I will check')<body.index('网页搜索')<body.index('md-message">Final weather')
    assert body.count('class="raw-message hideM"')==2
    copy='\n\n'.join(re.findall(r'<div class="raw-message hideM">(.*?)</div>',body,re.S))
    assert html.unescape(copy)=='I will check\n\nFinal weather'
    assert decode_rows(final,model._conversation_id)==model._display
    document=model.history_document(dict(history=model.history,chatbot=model._display))
    restored=transcript.loads(transcript.serialize(document),scope_id='import',imported=True)
    summaries=[entry for entry in restored['agent_transcript']['timeline'] if entry['kind']=='summary']
    assert summaries[0]['content']==[dict(type='summary_text',text='Check weather.')]
    assert 'HIDDEN' not in json.dumps(restored) and 'PRIVATE' not in json.dumps(restored)


def test_output_index_orders_late_arrival_and_done_stays_in_place():
    state=runtime.TurnState();state.accept(turn('created'))
    command=dict(id='tool',type='command_execution',turn_id='t1',status='in_progress',command='pwd')
    state.accept(item_event(command,2))
    state.accept(item_event(message('comment','before'),1))
    state.accept(item_event(reasoning('completed','public'),0))
    assert [item['id'] for item in state.snapshot()['items']]==['r','comment','tool']
    state.accept(item_event(dict(command,status='completed',output='/workspace'),2,'done'))
    data=transcript.normalize(state.snapshot()['items'],scope_id='scope')
    assert [entry['source_id'] for entry in transcript.render_input({'agent_transcript':data})['timeline']]==['r','comment','tool']


def test_monotonic_clocks_are_independent_freeze_and_do_not_guess_recovered_start(monkeypatch):
    current=[100.0];monkeypatch.setattr('modules.agent.activity.time.monotonic',lambda:current[0])
    clock=ActivityClock();a=dict(id='a',turn_id='t1',type='web_search_call',status='in_progress')
    b=dict(a,id='b');clock.observe(a,first=True)
    current[0]=101;clock.observe(b,first=True)
    current[0]=102;clock.observe(dict(a,status='completed'))
    current[0]=104;records={record['item_id']:record for record in clock.snapshot()}
    assert records['a']['elapsed_ms']==2000 and not records['a']['running']
    assert records['b']['elapsed_ms']==3000 and records['b']['running']
    clock.observe(a,first=True);current[0]=105
    assert clock.snapshot()[0]['elapsed_ms']==2000
    unknown=dict(a,id='recovered');clock.observe(unknown)
    assert clock.snapshot()[-1]['elapsed_ms'] is None
    clock.finish_turn('t1','cancelled');current[0]=120
    assert clock.snapshot()[1]['phase']=='turn_cancelled' and clock.snapshot()[1]['elapsed_ms']==4000


def test_summary_resume_delta_refreshes_snapshot_without_replaying_included_text():
    state=runtime.TurnState(session_id='sess_test')
    saved=dict(turn_id='t1',outcome='in_progress',items=[reasoning(text='snapshot')],required_actions=[],settings={},capture={'items':'complete'})
    runtime._seed(state,saved);state.snapshot_partial_ids={'r'}
    client=FakeClient();client.saved_items=[reasoning(text='snapshot included')]
    events=[event('reasoning_summary_text.delta',item_id='r',output_index=0,summary_index=0,delta=' included'),
            item_event(reasoning('completed','snapshot included'),0,'done'),turn('completed')]
    runtime._process_events(client,events,state,{},None,read_only=True)
    assert state.items['r']['summary'][0]['text']=='snapshot included'
    assert state.activity.snapshot()[0]['elapsed_ms'] is None


@pytest.mark.parametrize('outcome',['failed','cancelled'])
def test_turn_end_does_not_claim_unfinished_tool_success(outcome):
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(dict(id='w',type='web_search_call',turn_id='t1',status='in_progress'),0))
    state.accept(turn(outcome))
    record=state.activity.snapshot()[0]
    assert not record['running'] and record['phase']=='turn_'+outcome


def test_import_summary_strips_raw_reasoning_extra_fields_and_redacts_secrets():
    data=transcript.normalize([reasoning('completed','safe secret-value <script>x</script>')],scope_id='scope',secrets=('secret-value',))
    document=transcript.migrate(dict(history=[],chatbot=[],agent_transcript=data,history_format={'name':'chuanhu','version':2}),scope_id='scope')
    document['agent_transcript']['timeline'][0]['content'].append(dict(type='reasoning_text',text='RAW HIDDEN'))
    document['agent_transcript']['timeline'][0]['encrypted_content']='ENCRYPTED'
    imported=transcript.loads(json.dumps(document),scope_id='import',secrets=('secret-value',),imported=True)
    wire=json.dumps(imported)
    assert 'RAW HIDDEN' not in wire and 'ENCRYPTED' not in wire and 'secret-value' not in wire
    entry=imported['agent_transcript']['timeline'][0]
    from modules.agent.transcript_view import _activity
    output=_activity([entry])
    assert '<script>' not in output and '&lt;script&gt;' in output


def test_function_call_id_is_scoped_to_turn_and_waits_for_result():
    state=runtime.TurnState();state.accept(turn('created'))
    call=dict(id='call',type='function_call',turn_id='t1',status='completed',call_id='same',name='test',arguments={})
    state.accept(item_event(call,0,'done'))
    assert state.activity.snapshot()[0]['phase']=='waiting'
    wrong=dict(id='output-other',type='function_call_output',turn_id='other',call_id='same',output='other')
    state.accept(event('item.added',turn_id='other',item=wrong,output_index=1))
    assert state.activity.snapshot()[0]['phase']=='waiting'
    right=dict(wrong,id='output',turn_id='t1',output='done')
    state.accept(item_event(right,1))
    assert state.activity.snapshot()[0]['phase']=='completed'


def test_browser_elapsed_counter_contract():
    import subprocess
    result=subprocess.run(['node','tests/javascript/agent-activity.test.cjs'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_turn_time_data_remains_without_whole_turn_display():
    data=transcript.normalize([],scope_id='scope',turns=[dict(id='t1',status='completed',created_at=90,started_at=100,completed_at=102)])
    saved=transcript.loads(transcript.serialize({'agent_transcript':data}),scope_id='scope')['agent_transcript']
    assert saved['turns'][0]['started_at']==100 and saved['turns'][0]['completed_at']==102
    from pathlib import Path
    source=(Path(__file__).resolve().parents[2]/'modules/agent/transcript_view.py').read_text()
    assert '_turn_elapsed' not in source and 'agent-turn-elapsed' not in source


def test_summary_bounded_and_raw_reasoning_only_remains_excluded():
    source=reasoning('completed','x'*100000)
    source['summary'].append(dict(type='reasoning_text',text='NEVER PUBLIC'))
    data=transcript.normalize([source],scope_id='scope')
    entry=data['timeline'][0]
    assert entry['kind']=='summary' and entry['capture']['truncated']
    assert len(json.dumps(entry['content']).encode())<=transcript.MAX_TOOL_BYTES
    assert 'NEVER PUBLIC' not in transcript.serialize({'agent_transcript':data})
    assert transcript.normalize([dict(id='private',type='reasoning',content='NEVER')],scope_id='scope')['timeline']==[]


def test_ambiguous_function_call_id_does_not_complete_multiple_calls():
    state=runtime.TurnState();state.accept(turn('created'))
    for index in range(2):
        state.accept(item_event(dict(id='call'+str(index),type='function_call',turn_id='t1',status='completed',call_id='ambiguous',name='test',arguments={}),index,'done'))
    state.accept(item_event(dict(id='output',type='function_call_output',turn_id='t1',call_id='ambiguous',output='done'),2))
    records={record['item_id']:record for record in state.activity.snapshot()}
    assert records['call0']['phase']==records['call1']['phase']=='waiting'


def test_recovered_function_clock_starts_only_at_observed_execution(monkeypatch):
    current=[100.0];monkeypatch.setattr('modules.agent.activity.time.monotonic',lambda:current[0])
    clock=ActivityClock();call=dict(id='call',type='function_call',turn_id='t1',status='completed')
    clock.observe(call)
    assert clock.snapshot()[0]['elapsed_ms'] is None
    current[0]=110;clock.observe(call,phase='running')
    current[0]=112;clock.observe(call,phase='completed')
    assert clock.snapshot()[0]['elapsed_ms']==2000


def test_real_function_execution_emits_running_before_body_and_finished_before_result(tmp_path,monkeypatch):
    from modules.agent import tools
    from types import SimpleNamespace
    monkeypatch.setattr(tools,'_control_folder',lambda *args:tmp_path)
    phases=[];sent=[]
    def execute(arguments,stop):
        assert phases==['running'] and not sent
        return {'ok':True}
    tools.register_function('activity_order_test','Offline observation',{'type':'object'},execute)
    client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(events=SimpleNamespace(create=lambda *args,**kw:sent.append(kw))))))
    state=SimpleNamespace(session_id='sess_activity_test',turn_id='t1')
    action=dict(type='function_call',turn_id='t1',call_id='call',name='activity_order_test',arguments={})
    try:
        tools.handle_function_actions(client,state,{'required_actions':[action]},{'functions':['activity_order_test']},set(),on_activity=lambda action,phase:phases.append(phase))
        assert phases==['running','completed'] and len(sent)==1
    finally:
        tools.FUNCTIONS.pop('activity_order_test',None)
from copy import deepcopy
import pytest
from agent_fixtures import env
from test_runtime import FakeClient,event,turn,message
from modules.agent import runtime
from modules.agent.message_files import decode_rows


def test_actual_recover_fences_summary_and_command_deltas(env):
    r=reasoning(text='snapshot included')
    cmd=dict(id='cmd',type='command_execution',turn_id='t1',status='in_progress',command='pwd',output='snapshot included')
    events=[event('reasoning_summary_text.delta',item_id='r',output_index=0,summary_index=0,delta=' included',event_id='r1'),
      dict(type='agent.output.command_execution_output.delta',session_id='sess_test',turn_id='t1',item_id='cmd',output_index=1,delta=' included',event_id='c1')]
    client=FakeClient(events=events,session_status='in_progress',saved_turn='in_progress');client.saved_items=[r,cmd]
    snapshots=[]
    with pytest.raises(runtime.AgentError):runtime.recover_stream(client,'sess_test','t1',read_only=True,on_progress=lambda state:snapshots.append(deepcopy(state.snapshot())))
    entries={item['id']:item for item in snapshots[-1]['items']}
    assert (entries['r']['summary'][0]['text'],entries['cmd']['output'])==('snapshot included','snapshot included')
    assert entries['cmd']['output']=='snapshot included'


def test_late_commentary_preview_preserves_order(env):
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(message('u','question',role='user'),None))
    state.accept(item_event(message('final','FINAL'),2))
    state.accept(item_event(dict(id='tool',type='function_call',turn_id='t1',call_id='c',name='TOOL',arguments={},status='in_progress'),1))
    state.accept(item_event(message('comment','COMMENTARY'),0))
    model=model_for_stream(env);accept(model,state)
    html=rendered(model)[0][1]
    body=html[html.find('</div>')+6:]
    assert body.index('COMMENTARY')<body.index('TOOL')<body.index('FINAL'),body
    assert decode_rows(rendered(model),model._conversation_id)==model._display


def test_late_order_survives_done_reconcile_copy_and_decode(env):
    state=runtime.TurnState();state.accept(turn('created'))
    final=message('final','FINAL');comment=message('comment','COMMENTARY')
    tool=dict(id='tool',type='web_search_call',turn_id='t1',status='in_progress',action=dict(type='search',query='weather'))
    state.accept(item_event(final,2));state.accept(item_event(tool,1));state.accept(item_event(comment,0))
    assert state.text=='COMMENTARY\n\nFINAL'
    for item,index in ((final,2),(tool,1),(comment,0)):
        state.accept(item_event(dict(item,status='completed'),index,'done'))
    state.accept(turn('completed'))
    client=FakeClient(saved_turn='completed');client.saved_items=[dict(item,status='completed') for item in (final,tool,comment)]
    runtime._reconcile_terminal(client,state)
    assert state.text=='COMMENTARY\n\nFINAL'
    assert [item['id'] for item in state.snapshot()['items']]==['comment','tool','final']
    model=model_for_stream(env);accept(model,state)
    output=rendered(model);body=output[0][1]
    raw='\n\n'.join(re.findall(r'<div class="raw-message hideM">(.*?)</div>',body,re.S))
    assert html.unescape(raw)=='COMMENTARY\n\nFINAL'
    visible=body[body.find('</div>')+6:]
    assert visible.index('COMMENTARY')<visible.index('网页搜索')<visible.index('FINAL')
    assert decode_rows(output,model._conversation_id)==model._display


def test_cancelled_activity_hides_stop_label_keeps_timer_frozen_and_failure_visible():
    from modules.agent.transcript_view import _activity
    item=dict(id='cmd',type='command_execution',turn_id='t1',status='in_progress',command='pwd')
    data=transcript.normalize([item],scope_id='scope')
    entry=data['timeline'][0]
    cancelled=_activity([entry],clock={'cmd':dict(phase='turn_cancelled',elapsed_ms=1200,running=False)},active=True)
    assert 'pwd' in cancelled and '代码与文件执行' not in cancelled
    assert 'agent-activity-status' not in cancelled and 'aria-label="pwd · 本轮已停止"' in cancelled
    assert 'agent-activity-elapsed' not in cancelled
    failed=_activity([entry],clock={'cmd':dict(phase='turn_failed',elapsed_ms=1200,running=False)},active=True)
    assert '本轮失败' in failed
    waiting=_activity([entry],clock={'cmd':dict(phase='waiting',elapsed_ms=1200,running=False)},active=True)
    assert '等待结果' in waiting


def test_ue_titles_use_api_name_title_and_specific_web_action():
    from modules.agent.transcript_view import _activity
    items=[dict(id='f',turn_id='t1',type='function_call',name='actual_function',call_id='f',arguments={},status='completed'),
           dict(id='m',turn_id='t1',type='mcp_call',name='actual_mcp',server_label='server',arguments={},status='completed'),
           dict(id='c',turn_id='t1',type='computer_use_call',title='Actual computer title',status='completed')]
    for index,action in enumerate(('search','open_page','find_in_page')):
        items.append(dict(id='web'+str(index),turn_id='t1',type='web_search_call',action={'type':action},status='completed'))
    entries=transcript.normalize(items,scope_id='scope')['timeline']
    markup=_activity(entries)
    for title in ('actual_function','actual_mcp','Actual computer title','网页搜索','打开网页','页内查找'):
        assert '>'+title+'</span>' in markup
    assert '网页搜索与浏览' not in markup and 'agent-activity-status' not in markup


def test_tool_details_keep_native_type_and_only_disambiguate_colliding_mcp_servers():
    from modules.agent.transcript_view import _activity
    items=[dict(id='a',turn_id='t1',type='mcp_call',name='lookup',server_label='alpha',status='completed'),
           dict(id='b',turn_id='t1',type='mcp_call',name='lookup',server_label='beta',status='completed')]
    entries=transcript.normalize(items,scope_id='scope')['timeline']
    markup=_activity(entries)
    assert '>lookup · alpha</span>' in markup and '>lookup · beta</span>' in markup
    assert '&quot;type&quot;: &quot;mcp_call&quot;' in markup
    alone=_activity(entries[:1])
    assert '>lookup</span>' in alone and '>lookup · alpha</span>' not in alone


def test_status_and_capture_alert_hooks_exclude_running_from_full_alpha_alerts():
    from modules.agent.transcript_view import _activity
    entry=transcript.normalize([dict(id='cmd',type='command_execution',turn_id='t1',status='in_progress',command='pwd')],scope_id='scope')['timeline'][0]
    entry['capture']['omitted']=True;entry['capture']['truncated']=True
    for phase in ('running','waiting','failed','turn_failed','incomplete','unknown'):
        markup=_activity([entry],clock={'cmd':dict(phase=phase,elapsed_ms=1000,running=False)})
        assert 'data-phase="'+phase+'"' in markup
        assert '<small class="agent-activity-notice">' in markup
        assert '部分内容未保存' in markup and '内容已截断' in markup


def test_no_visible_phase_labels_native_summary_has_accessible_state_and_error_evidence():
    import re
    from modules.agent.transcript_view import _activity
    entry=transcript.normalize([dict(id='m',type='mcp_call',turn_id='t1',name='actual_tool',status='failed',error={'message':'actual API error'})],scope_id='scope')['timeline'][0]
    entry['capture']['omitted']=True
    for phase in ('running','waiting','completed','failed','turn_failed','incomplete','unknown','cancelled','turn_cancelled'):
        output=_activity([entry],clock={'m':dict(phase=phase,elapsed_ms=1000,running=False)})
        summary=re.search(r'<summary[^>]*>(.*?)</summary>',output).group(1)
        assert re.sub('<[^>]+>','',summary).strip()=='actual_tool'
        assert 'agent-activity-status' not in output and 'aria-live' not in output
        assert 'aria-label="actual_tool · ' in output and 'data-phase="'+phase+'"' in output
        assert 'actual API error' in output and '部分内容未保存' in output
        assert '<details ' in output and 'role="button"' not in output
