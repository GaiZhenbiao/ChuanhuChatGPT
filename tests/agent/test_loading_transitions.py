"""Scoped ongoing-work indication, without interpreting message text as status."""
import pytest
from agent_fixtures import env
from test_single_reply_bubble import model, update, command, render
from test_runtime import message
from test_postprocess_roundtrip import converters, postprocess
from modules.agent.ui import AgentPanel
from modules.agent.message_files import decode_rows


def assert_waiting(m, waiting, empty=False):
    markup=render(m)[0][1]
    assert ('data-waiting="true"' in markup) is waiting
    assert ('data-empty="true"' in markup) is empty


def test_empty_sentence_tool_between_tools_and_final_text(env):
    m=model(env);user=message('u','question',role='user')
    update(m,[user],history_authoritative=True)
    assert_waiting(m,True,True)
    ns=converters();rows=AgentPanel(ns['convert_user_before_marked'],ns['convert_bot_before_marked']).render_chat(m,m._display)
    assert 'agent-body-segment' not in rows[0][1]
    assert '<div class="agent-format-receipt hideM" hidden>' in rows[0][1]
    assert postprocess(rows,ns)==rows
    assert decode_rows(rows,m._conversation_id)==m._display
    sentence=message('a','I will prepare a file.')
    update(m,[user,sentence],history_authoritative=True)
    assert_waiting(m,True)
    update(m,[user,sentence,command()],history_authoritative=True)
    assert_waiting(m,False)
    update(m,[user,sentence,command(status='completed')],history_authoritative=True)
    assert_waiting(m,True)
    update(m,[user,sentence,command(status='completed'),command('next')],history_authoritative=True)
    assert_waiting(m,False)
    link=message('final','[Download](sandbox:/mnt/data/report.txt)')
    update(m,[user,sentence,command(status='completed'),command('next',status='completed'),link],history_authoritative=True)
    assert_waiting(m,True)
    assert m._state['outcome']=='in_progress' and not m._artifacts
    for outcome in ('completed','failed','cancelled','not_started'):
        m._state['outcome']=outcome
        assert_waiting(m,False)


def test_other_turn_tools_and_ambiguous_phases_do_not_hide_current_waiting(env):
    m=model(env);user=message('u','question',role='user')
    update(m,[user,message('a','Working'),command(turn='other')],history_authoritative=True)
    assert_waiting(m,True)
    update(m,[user,message('a','Working'),command(status='incomplete')],history_authoritative=True)
    assert_waiting(m,True)


@pytest.mark.parametrize('phase,waiting',[('running',False),('waiting',False),('completed',True),('failed',True)])
def test_observed_tool_phase_is_shared_with_visible_tool_state(env,phase,waiting):
    m=model(env)
    update(m,[message('u','question',role='user'),message('a','Working'),command()],history_authoritative=True)
    m._activity_records=[dict(item_id='cmd',turn_id='t1',phase=phase,running=phase in ('running','waiting'))]
    assert_waiting(m,waiting)


def test_public_text_deltas_hide_dots_until_explicit_part_done_without_completing_turn(env):
    from modules.agent.runtime import TurnState
    from test_runtime import event, turn, text
    state=TurnState();state.accept(turn('created'))
    m=model(env)
    def consume(value):
        state.accept(value)
        assert m._accept(dict(type='progress',**state.snapshot()),'g')
    consume(event('item.added',item=message('u','question',role='user')))
    assert_waiting(m,True,True)
    consume(event('item.added',output_index=0,item=message('a','',status='in_progress')))
    assert_waiting(m,True,True)
    for chunk in ['Working', ' on', ' this.']:
        consume(text('delta',chunk,item='a'))
        assert_waiting(m,False)
        # Repeated snapshots and unrelated file progress cannot flash dots
        # between tokens. Only explicit public-text phase events change it.
        assert m._accept(dict(type='progress',**state.snapshot()),'g')
        assert m._accept(dict(type='progress',session_id='sess_test',artifacts=[]),'g')
        assert_waiting(m,False)
    consume(text('done','Working on this.',item='a'))
    assert_waiting(m,True)
    assert state.items['a']['status']=='in_progress'
    assert 'a' not in state.final_items and not state.turn_complete
    consume(event('item.done',output_index=0,item=message('a','Working on this.')))
    assert_waiting(m,True)
    consume(event('item.added',output_index=1,item=command()))
    assert_waiting(m,False)
    consume(event('item.done',output_index=1,item=command(status='completed')))
    assert_waiting(m,True)
    consume(event('item.added',output_index=2,item=message('b','',status='in_progress')))
    consume(event('output_text.delta',item_id='b',output_index=2,content_index=0,delta='Final'))
    assert_waiting(m,False)
    consume(event('content_part.done',item_id='b',output_index=2,content_index=0,part=dict(type='output_text',text='Final')))
    assert_waiting(m,True)
    assert not state.turn_complete and state.items['b']['status']=='in_progress'


def test_multipart_text_receipt_does_not_end_other_open_segment():
    from modules.agent.runtime import TurnState
    from test_runtime import event, turn
    state=TurnState();state.accept(turn('created'))
    for index in (0,1):
        state.accept(event('output_text.delta',item_id='a',output_index=0,content_index=index,delta='part'))
    state.accept(event('output_text.done',item_id='a',output_index=0,content_index=0,text='part'))
    assert state.snapshot()['public_text_streaming']
    state.accept(event('output_text.done',item_id='a',output_index=0,content_index=1,text='part'))
    assert not state.snapshot()['public_text_streaming']
    assert state.items['a']['status']=='in_progress' and not state.final_items


@pytest.mark.parametrize('outcome',['completed','failed','cancelled'])
def test_terminal_always_clears_public_text_view_flag(outcome):
    from modules.agent.runtime import TurnState
    state=TurnState(outcome=outcome);state.streaming_text_parts.add(('message',0))
    assert not state.snapshot()['public_text_streaming']


def test_older_snapshot_status_compatibility_and_generation_guard(env):
    m=model(env);user=message('u','question',role='user')
    update(m,[user,message('a','Streaming',status='in_progress')],history_authoritative=True)
    assert_waiting(m,False)
    update(m,[user,message('a','Streaming')],history_authoritative=True)
    assert_waiting(m,True)
    assert not m._accept(dict(type='progress',session_id='sess_test',turn_id='t1',public_text_streaming=True),'stale')
    assert_waiting(m,True)


def test_reconnect_overlap_get_completion_clears_only_view_stream_phase():
    from types import SimpleNamespace
    from modules.agent.runtime import TurnState, AgentError, _process_events, _seed
    from test_runtime import event
    state=TurnState(session_id='sess_test',turn_id='t1',outcome='in_progress')
    state.items['a']=message('a','Partial',status='in_progress')
    state.snapshot_partial_ids={'a'};state.streaming_text_parts.add(('a',0))
    endpoint=SimpleNamespace(list=lambda *args,**kwargs:[message('a','Complete')])
    client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(items=endpoint))))
    frames=[]
    with pytest.raises(AgentError, match='连接已中断'):
        _process_events(client,[event('output_text.delta',item_id='a',output_index=0,content_index=0,delta='Complete')],state,{},lambda s:frames.append(s.snapshot()))
    assert frames and not frames[-1]['public_text_streaming']
    assert not state.streaming_text_parts
    assert state.items['a']['content'][0]['text']=='Complete'
    assert 'a' not in state.final_items and not state.turn_complete
    state.streaming_text_parts.add(('a',0))
    _seed(state,dict(turn_id='t1',outcome='in_progress',items=[message('a','Still partial',status='in_progress')],required_actions=[],settings={}))
    assert not state.streaming_text_parts and not state.snapshot()['public_text_streaming']
