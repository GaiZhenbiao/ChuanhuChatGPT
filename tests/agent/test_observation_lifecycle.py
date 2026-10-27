"""Retained provider facts survive partial snapshots and fresh-client recovery."""
from copy import deepcopy
import json
import pytest
from modules.agent import runtime
from test_runtime import FakeClient
from test_terminal_integrity import accepted,started,terminal,final,item,reasoning,event


def receipt(state): return json.loads(json.dumps(state.snapshot()['observation']))
def body(value): return repr(value.items)
def full(group):
    return item(text='First known') if group == 'content' else reasoning(['First known'])
def with_second(group):
    value=full(group);value[group].append(dict(type='output_text' if group=='content' else 'summary_text',text='Second known'))
    return value

def recover(state,values,observation=None,agent='agent_one'):
    client=FakeClient();client.saved_items=deepcopy(values)
    client.beta.agents.sessions.turns.retrieve=lambda identifier,**kw:dict(id=identifier,session_id=kw['session_id'],agent_id=agent,status='completed')
    return runtime.recover_stream(client,state.session_id,state.turn_id,observation=observation if observation is not None else receipt(state))

@pytest.mark.parametrize('group',['content','summary'])
@pytest.mark.parametrize('kind',['item.added','item.updated','item.done'])
@pytest.mark.parametrize('sealed',[False,True])
@pytest.mark.parametrize('short_kind',['missing','empty','first'])
def test_known_body_and_minimum_shape_survive_every_snapshot_and_fresh_client(group,kind,sealed,short_kind):
    value=with_second(group)
    state=accepted(started(),event('item.done' if sealed else 'item.added',output_index=0,item=value))
    short=deepcopy(value)
    if short_kind=='missing':short.pop(group)
    else:short[group]=short[group][:1] if short_kind=='first' else []
    if kind!='item.done':short['status']='in_progress'
    state.accept(event(kind,event_id='short',output_index=0,item=short));state.accept(terminal())
    assert not state.turn_complete and 'Second known' in body(state)
    stale=recover(state,[full(group)])
    assert stale.sync_complete is False and 'Second known' in body(stale)
    rewritten=with_second(group)
    for index,part in enumerate(rewritten[group]):part['text']='Canonical rewrite '+str(index)
    settled=recover(stale,[rewritten])
    assert settled.sync_complete and 'Canonical rewrite 1' in body(settled)
    assert 'Second known' not in body(settled)

@pytest.mark.parametrize('change',['agent','role','type','turn','part'])
def test_repeated_conflicting_reads_do_not_rebind_or_poison_the_original_receipt(change):
    state=accepted(started(),final(with_second('content')),terminal())
    wrong=with_second('content');agent='agent_one'
    if change=='agent':agent='agent_other';wrong['content'].append(dict(type='output_text',text='Foreign extra'))
    elif change=='role':wrong['role']='user'
    elif change=='type':wrong['type']='reasoning';wrong['summary']=[]
    elif change=='part':wrong['content'][1]['type']='text'
    else:wrong['turn_id']='other_turn'
    pending=recover(state,[wrong],agent=agent)
    again=recover(pending,[wrong],agent=agent)
    assert pending.sync_complete is False and again.sync_complete is False
    assert 'Second known' in body(again)
    good=recover(again,[with_second('content')])
    assert good.sync_complete and 'Second known' in body(good)

@pytest.mark.parametrize('unknown',['event','budget'])
def test_unverifiable_observation_is_not_erased_by_worker_replacement(monkeypatch,unknown):
    state=accepted(started())
    if unknown=='budget':
        monkeypatch.setattr(runtime,'MAX_OBSERVED_PARTS',1)
        state.accept(event('output_text.delta',item_id='answer',output_index=0,content_index=0,delta='First'))
        state.accept(event('output_text.delta',event_id='next',item_id='answer',output_index=0,content_index=1,delta='Second'))
    else:state.accept(event('future_payload',item_id='answer'))
    state.accept(final(item()));state.accept(terminal())
    recovered=recover(state,[with_second('content')])
    assert recovered.sync_complete is False and recovered.unverifiable_stream

@pytest.mark.parametrize('change',['session','root','duplicate','shape'])
def test_malformed_private_receipt_cannot_silently_remove_constraints(change):
    state=accepted(started(),final(with_second('content')),terminal());stored=receipt(state)
    if change=='session':stored['session_id']='other_session'
    elif change=='root':stored['turns'][0]['root_identity'][1]='other_turn'
    elif change=='duplicate':stored['turns'].append(deepcopy(stored['turns'][0]))
    else:stored['turns'][0]['parts'][0]['shapes'][0][1]=False
    with pytest.raises(runtime.AgentError):recover(state,[full('content')],observation=stored)


def test_new_turn_fast_commit_keeps_previous_shape_without_extra_get():
    first=accepted(started(),final(with_second('content')),terminal())
    continued=runtime.TurnState(session_id=first.session_id);continued.restore_observation(receipt(first))
    turn=dict(id='turn_two',session_id=first.session_id,agent_id='agent_two',status='in_progress')
    continued.accept(event('created',event_id='new_root',turn_id='turn_two',turn=turn))
    answer=dict(item(identifier='new_answer'),turn_id='turn_two')
    continued.accept(event('item.done',event_id='new_answer',turn_id='turn_two',output_index=0,item=answer))
    continued.accept(event('completed',event_id='new_terminal',turn_id='turn_two',turn=dict(turn,status='completed')))
    assert continued.turn_complete
    roots={first.turn_id:dict(id=first.turn_id,session_id=first.session_id,agent_id='agent_one',status='completed'),
           'turn_two':dict(turn,status='completed')}
    client=FakeClient();client.saved_items=[full('content'),answer]
    client.beta.agents.sessions.turns.retrieve=lambda identifier,**kw:roots[identifier]
    pending=runtime.recover_stream(client,continued.session_id,continued.turn_id,observation=receipt(continued))
    assert pending.sync_complete is False and 'Second known' in body(pending)
    client=FakeClient();client.saved_items=[with_second('content'),answer]
    client.beta.agents.sessions.turns.retrieve=lambda identifier,**kw:roots[identifier]
    settled=runtime.recover_stream(client,continued.session_id,continued.turn_id,observation=receipt(pending))
    assert settled.sync_complete
