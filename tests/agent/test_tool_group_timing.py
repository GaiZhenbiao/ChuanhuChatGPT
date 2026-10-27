"""Observed wall span, grouping and offline history/DOM integration."""
import pytest
from agent_fixtures import env
from modules.agent import transcript, runtime
from modules.agent.activity import ActivityClock, safe_records, group_span
from modules.agent.transcript_view import _tool_runs, _tool_group, i18n
from test_realtime_activity import model_for_stream, accept, rendered, item_event
from test_runtime import turn, message


@pytest.fixture
def clock(monkeypatch):
    now=[100.0]
    monkeypatch.setattr('modules.agent.activity.time.monotonic',lambda:now[0])
    return now,ActivityClock()


def command(key='a',status='in_progress',**extra):
    return dict(id=key,turn_id='t1',type='command_execution',status=status,command='pwd',**extra)


def snapshot(items, clock, **extra):
    return transcript.normalize(items,scope_id='scope',activity=clock.snapshot(),**extra)


def groups(data):
    return [group for group in _tool_runs(data['timeline'],'scope') if group['kind']=='tool_group']


def test_parallel_tools_use_wall_span_not_sum_and_terminal_sample_is_not_end(clock):
    now,c=clock;a,b=command('a'),command('b')
    c.observe(a,first=True);now[0]=102;c.observe(b,first=True)
    now[0]=105;c.observe(dict(a,status='completed'))
    now[0]=107;c.observe(dict(b,status='completed'));now[0]=200
    data=snapshot([dict(a,status='completed'),dict(b,status='completed')],c)
    assert group_span(groups(data)[0])==dict(elapsed_ms=7000,running=False)
    assert sum(record['elapsed_ms'] for record in c.snapshot())==10000
    interval=c.snapshot()[0]['interval']
    assert interval['started_ms']==0 and interval['ended_ms']==5000 and interval['sampled_ms']==100000
    assert data['timeline'][0]['tool_group_duration']['elapsed_ms']==7000


@pytest.mark.parametrize('separator',[
    message('comment','Body between tools'),
    dict(id='summary',type='reasoning',turn_id='t1',summary=[dict(type='summary_text',text='Public summary')]),
])
def test_body_and_summary_break_groups_into_independent_durations(clock,separator):
    now,c=clock
    c.observe(command('a'),first=True);now[0]=103;c.observe(command('a','completed'))
    now[0]=120;c.observe(command('b'),first=True);now[0]=124;c.observe(command('b','completed'))
    data=snapshot([command('a','completed'),separator,command('b','completed')],c)
    assert [group_span(group)['elapsed_ms'] for group in groups(data)]==[3000,4000]
    assert [entry['tool_group_duration']['elapsed_ms'] for entry in data['timeline'] if 'tool_group_duration' in entry]==[3000,4000]


def test_appending_tool_extends_same_group_and_merge_recomputes_membership(clock):
    now,c=clock;c.observe(command('a'),first=True)
    now[0]=102;c.observe(command('a','completed'));original=snapshot([command('a','completed')],c)
    now[0]=106;c.observe(command('b'),first=True);now[0]=110;c.observe(command('b','completed'))
    merged=transcript.merge(original,snapshot([command('b','completed')],c))
    group=groups(merged)[0]
    assert group['id']==groups(original)[0]['id']
    receipt=merged['timeline'][0]['tool_group_duration']
    assert receipt['elapsed_ms']==10000 and receipt['members']==[entry['id'] for entry in group['entries']]
    split=snapshot([command('a','completed'),message('comment','new boundary'),command('b','completed')],c,capture={'items':'complete'})
    rebuilt=transcript.merge(merged,split,authoritative=True)
    assert [group_span(group)['elapsed_ms'] for group in groups(rebuilt)]==[2000,4000]


@pytest.mark.parametrize('outcome',['cancelled','failed','completed'])
def test_running_group_requires_live_receipt_and_turn_end_freezes_exact_end(clock,outcome):
    now,c=clock;c.observe(command(),first=True);now[0]=107.75
    data=snapshot([command()],c);group=groups(data)[0]
    records={record['item_id']:record for record in safe_records(c.snapshot())}
    assert group_span(group,clock=records,active=True)==dict(elapsed_ms=7750,running=True)
    assert group_span(group) is None and 'tool_group_duration' not in data['timeline'][0]
    c.finish_turn('t1',outcome);now[0]=300;frozen=snapshot([command()],c)
    assert group_span(groups(frozen)[0])==dict(elapsed_ms=7750,running=False)
    assert frozen['timeline'][0]['activity_phase']=={'cancelled':'turn_cancelled','failed':'turn_failed','completed':'incomplete'}[outcome]


def test_saved_terminal_group_restores_without_restarting_clock_or_losing_turn_dates(clock):
    now,c=clock;c.observe(command(),first=True);now[0]=167.9;c.observe(command(status='completed'))
    data=snapshot([command(status='completed')],c,turns=[dict(id='t1',status='completed',started_at=100,completed_at=167.9)])
    restored=transcript.loads(transcript.serialize({'agent_transcript':data}),scope_id='scope')['agent_transcript']
    assert restored['timeline'][0]['tool_group_duration']['elapsed_ms']==pytest.approx(67900)
    now[0]=10000
    assert group_span(groups(restored)[0])['elapsed_ms']==pytest.approx(67900)
    assert restored['turns'][0]['started_at']==100 and restored['turns'][0]['completed_at']==167.9
    assert 'data-running="false"' in _tool_group(groups(restored)[0],scope='scope',conversation='chat',active=True)


def test_authoritative_history_get_keeps_matching_observation_interval(clock):
    now,c=clock;c.observe(command(),first=True);now[0]=103;c.observe(command(status='completed'))
    saved=snapshot([command(status='completed')],c)
    retrieved=transcript.normalize([command(status='completed')],scope_id='scope',capture={'items':'complete'})
    merged=transcript.merge(saved,retrieved,authoritative=True)
    assert merged['timeline'][0]['tool_group_duration']['elapsed_ms']==3000
    assert merged['timeline'][0]['activity_interval']==saved['timeline'][0]['activity_interval']


def test_import_remaps_group_member_receipts_and_missing_appended_interval_invalidates_cache(clock):
    now,c=clock;c.observe(command(),first=True);now[0]=103;c.observe(command(status='completed'))
    data=snapshot([command(status='completed')],c)
    imported=transcript.loads(transcript.serialize({'agent_transcript':data}),scope_id='import-scope',imported=True)
    view=transcript.render_input(imported)
    receipt=view['timeline'][0]['tool_group_duration']
    assert receipt['elapsed_ms']==3000 and receipt['members']==[view['timeline'][0]['id']]
    assert receipt['members']!=data['timeline'][0]['tool_group_duration']['members']
    incoming=transcript.normalize([command('missing','completed')],scope_id='scope')
    merged=transcript.merge(data,incoming)
    assert 'tool_group_duration' not in merged['timeline'][0] and group_span(groups(merged)[0]) is None


def test_zero_monotonic_terminal_value_is_not_replaced_with_later_sample(monkeypatch):
    now=[0.0];monkeypatch.setattr('modules.agent.activity.time.monotonic',lambda:now[0])
    c=ActivityClock();c.observe(command(),first=True);c.observe(command(status='completed'))
    now[0]=10
    assert c.snapshot()[0]['elapsed_ms']==0
    assert group_span(groups(snapshot([command(status='completed')],c))[0])==dict(elapsed_ms=0,running=False)


def test_recovered_worker_and_mixed_domains_do_not_reconstruct_missing_start(clock):
    now,c=clock;c.observe(command('a'),first=True);now[0]=103;c.observe(command('a','completed'))
    fresh=ActivityClock();fresh.observe(command('b'));now[0]=107;fresh.observe(command('b','completed'))
    records=c.snapshot()+fresh.snapshot()
    data=transcript.normalize([command('a','completed'),command('b','completed')],scope_id='scope',activity=records)
    assert group_span(groups(data)[0]) is None and 'interval' not in records[-1]
    fresh=ActivityClock();fresh.observe(command('b'),first=True);now[0]=110;fresh.observe(command('b','completed'))
    data=transcript.normalize([command('a','completed'),command('b','completed')],scope_id='scope',activity=c.snapshot()+fresh.snapshot())
    assert group_span(groups(data)[0]) is None and 'tool_group_duration' not in data['timeline'][0]


def test_legacy_duration_and_ambiguous_identity_do_not_guess_group_time(clock):
    now,c=clock;c.observe(command(),first=True);now[0]=103;c.observe(command(status='completed'))
    legacy=transcript.normalize([command(status='completed',elapsed_ms=3000,duration_ms=3000)],scope_id='scope')
    assert group_span(groups(legacy)[0]) is None
    good=snapshot([command(status='completed')],c);good['timeline'][0]['identity']='unresolved'
    assert group_span(groups(good)[0]) is None
    bad=snapshot([command(status='completed')],c);bad['timeline'][0]['activity_interval']['ended_ms']=float('nan')
    validated=transcript.render_input({'agent_transcript':bad})
    assert group_span(groups(validated)[0]) is None


@pytest.mark.parametrize('language,text',[
    ('zh_CN','1分7秒'),('en_US','1m 7s'),('ja_JP','1分7秒'),('ko_KR','1분 7초'),
    ('ru_RU','1 мин 7 с'),('sv_SE','1 min 7 s'),('vi_VN','1 phút 7 giây'),
])
def test_minutes_are_localized_and_child_header_has_no_timer(clock,language,text):
    now,c=clock;c.observe(command(),first=True);now[0]=167.9;c.observe(command(status='completed'))
    data=snapshot([command(status='completed')],c)
    previous=i18n.language;i18n.change_language(language)
    try:
        output=_tool_group(groups(data)[0],scope='scope',conversation='chat')
        assert f'>{text}</span>' in output and output.count('agent-activity-elapsed')==1
        assert 'agent-activity-elapsed' not in output.split('<div class="agent-tool-list">',1)[1]
        assert 'width="12" height="12"' in output
    finally:i18n.change_language(previous)


def test_actual_runtime_projection_removes_top_timer_and_persists_group_duration(env,monkeypatch):
    now=[100.0];monkeypatch.setattr('modules.agent.activity.time.monotonic',lambda:now[0])
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(message('u','question',role='user'),None));state.accept(item_event(command(),0))
    model=model_for_stream(env);now[0]=107;accept(model,state)
    live=rendered(model)[0][1]
    assert live.count('agent-activity-elapsed')==1 and '>7s</span>' in live and 'data-running="true"' in live
    now[0]=107.9;state.accept(item_event(command(status='completed',exit_code=0),0,'done'))
    state.accept(item_event(message('answer','Finished'),1,'done'))
    terminal=turn('completed');terminal['turn'].update(started_at=100,completed_at=107.9)
    state.accept(terminal);accept(model,state);output=rendered(model)[0][1]
    assert 'agent-turn-elapsed' not in output and '本轮处理' not in output
    assert output.count('agent-activity-elapsed')==1 and '>7s</span>' in output and 'data-running="false"' in output
    saved=transcript.loads(transcript.serialize(model.history_document({'history':model.history,'chatbot':model._display})),scope_id=model._conversation_id)
    assert any('tool_group_duration' in entry for entry in saved['agent_transcript']['timeline'])
