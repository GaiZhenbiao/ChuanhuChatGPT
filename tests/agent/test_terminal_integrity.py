"""Known segment coverage and root identity constrain terminal admission."""
from copy import deepcopy
import pytest
from modules.agent import runtime
from test_finalization_boundary import complete_state, event as base_event, item
from test_runtime import FakeClient


def event(kind, **fields):
    value=base_event(kind);value.update(fields)
    return value

def accepted(*events):
    state=runtime.TurnState()
    for value in events:state.accept(value)
    return state

def started(**changes):
    turn=dict(id='turn_one',session_id='sess_one',agent_id='agent_one',status='in_progress')
    turn.update(changes)
    return event('created',turn=turn)

def terminal(**changes):
    turn=dict(id='turn_one',session_id='sess_one',agent_id='agent_one',status='completed')
    turn.update(changes)
    return event('completed',turn=turn)

def final(value,index=0):return event('item.done',output_index=index,item=value)

def retrieve(state,values):
    client=FakeClient(saved_turn='completed');client.saved_items=values
    runtime._reconcile_terminal(client,state)
    return state

def reasoning(parts):
    return dict(id='reason',type='reasoning',turn_id='turn_one',status='completed',summary=[dict(type='summary_text',text=text) for text in parts])

@pytest.mark.parametrize('kind',['output_text.delta','output_text.done','content_part.added','content_part.done','reasoning_summary_text.delta','reasoning_summary_part.added','reasoning_summary_part.done'])
@pytest.mark.parametrize('full_get',[False,True])
def test_missing_observed_part_requires_complete_get(kind,full_get):
    summary=kind.startswith('reasoning_')
    state=accepted(started())
    value=reasoning(['first']) if summary else item(text='first')
    if summary:state.accept(event('item.added',event_id='add_reason',output_index=0,item=dict(reasoning([]),status='in_progress')))
    fields=dict(item_id='reason' if summary else 'answer',output_index=0)
    fields['summary_index' if summary else 'content_index']=1
    if kind.endswith('.delta'):fields['delta']='second known'
    elif kind.endswith('text.done'):fields['text']='second known'
    else:fields['part']=dict(type='summary_text' if summary else 'output_text',text='second known')
    state.accept(event(kind,**fields));state.accept(final(value));state.accept(terminal())
    assert not state.turn_complete
    assert 'second known' in repr(state.snapshot()['items'])
    full=deepcopy(value)
    full['summary' if summary else 'content'].append(dict(type='summary_text' if summary else 'output_text',text='second known'))
    retrieve(state,[full if full_get else value])
    assert state.sync_complete is full_get
    assert 'second known' in repr(state.snapshot()['items'])

@pytest.mark.parametrize('change',['start_session','start_turn','start_agent_empty','terminal_agent','terminal_agent_empty','terminal_session','terminal_turn','outer_terminal_session','repeated_start_agent'])
def test_root_identity_conflicts_never_admit_from_stream(change):
    start=started()
    if change=='start_session':start['turn']['session_id']='conflict'
    if change=='start_turn':start['turn']['id']='conflict'
    if change=='start_agent_empty':start['turn']['agent_id']=''
    state=accepted(start,final(item()))
    if change=='repeated_start_agent':state.accept(dict(started(agent_id='conflict'),event_id='different_start'))
    end=terminal()
    if change=='terminal_agent':end['turn']['agent_id']='conflict'
    if change=='terminal_agent_empty':end['turn']['agent_id']=''
    if change=='terminal_session':end['turn']['session_id']='conflict'
    if change=='terminal_turn':end['turn']['id']='conflict'
    if change=='outer_terminal_session':end['session_id']='conflict'
    state.accept(end)
    assert not state.turn_complete and state.root_identity_conflict


def test_unrelated_foreign_session_does_not_corrupt_complete_current_turn():
    state=accepted(started(),final(item()))
    foreign=terminal(id='other_turn',session_id='other_session');foreign.update(session_id='other_session',turn_id='other_turn')
    state.accept(foreign);state.accept(terminal())
    assert state.turn_complete and not state.root_identity_conflict

@pytest.mark.parametrize('kind',['content_part.done','output_text.delta','reasoning_summary_part.done','reasoning_summary_text.delta'])
def test_new_part_after_item_done_still_prevents_early_completion(kind):
    summary=kind.startswith('reasoning_')
    value=reasoning(['first']) if summary else item(text='first')
    state=accepted(started(),final(value))
    fields=dict(item_id=value['id'],output_index=0)
    fields['summary_index' if summary else 'content_index']=1
    if kind.endswith('delta'):fields['delta']='late second'
    else:fields['part']=dict(type='summary_text' if summary else 'output_text',text='late second')
    state.accept(event(kind,**fields));state.accept(terminal())
    assert not state.turn_complete and 'late second' in repr(state.snapshot()['items'])


def test_full_authoritative_final_replacement_preserves_fast_turn_and_wins_lagging_get():
    state=accepted(started())
    for index in range(2):state.accept(event('output_text.delta',event_id='delta_'+str(index),item_id='answer',output_index=0,content_index=index,delta='earlier stream text'))
    final_item=item(text='rewritten first');final_item['content'].append(dict(type='output_text',text='rewritten second'))
    state.accept(final(final_item));state.accept(terminal())
    assert state.turn_complete and state.text=='rewritten first\nrewritten second'
    retrieve(state,[item(text='lagging partial')])
    assert state.sync_complete and state.text=='rewritten first\nrewritten second'


def test_richer_get_is_authority_when_stream_did_not_observe_additional_part():
    state=complete_state();full=item(text='GET first');full['content'].append(dict(type='output_text',text='GET second'))
    retrieve(state,[full])
    assert state.sync_complete and state.text=='GET first\nGET second'


def test_root_conflict_cannot_override_authoritative_get_text():
    state=accepted(started(),final(item(text='conflicting stream')),terminal(agent_id='conflict'))
    retrieve(state,[item(text='authoritative GET')])
    assert state.sync_complete and state.text=='authoritative GET'


def test_initial_part_without_text_can_be_completed_without_false_conflict():
    initial=dict(item(),status='in_progress',content=[dict(type='output_text')])
    state=accepted(started(),event('item.added',output_index=0,item=initial))
    state.accept(event('output_text.delta',item_id='answer',output_index=0,content_index=0,delta='partial'))
    state.accept(final(item(text='authoritative replacement')));state.accept(terminal())
    assert state.turn_complete and state.text=='authoritative replacement'
