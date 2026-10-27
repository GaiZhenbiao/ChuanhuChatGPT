"""Every accepted GET fact remains attached to its original turn across reads."""
from copy import deepcopy
import json
import pytest
from modules.agent import runtime
from test_runtime import FakeClient
from test_terminal_integrity import accepted, started, final, terminal, item, reasoning, event


def receipt(state): return json.loads(json.dumps(state.snapshot()['observation']))
def answer(group, texts, turn='turn_one', identifier='answer'):
    value = item(identifier=identifier) if group == 'content' else reasoning([])
    value.update(id=identifier, turn_id=turn)
    value[group] = [dict(type='output_text' if group == 'content' else 'summary_text', text=text) for text in texts]
    return value

def recover(state, values, root_status='completed', wrong_root=False):
    client=FakeClient();client.saved_items=deepcopy(values)
    client.beta.agents.sessions.turns.retrieve=lambda identifier, **kw: dict(
        id=identifier, session_id=kw['session_id'], agent_id='wrong' if wrong_root else 'agent_two' if identifier=='turn_two' else 'agent_one', status=root_status)
    return runtime.recover_stream(client, state.session_id, state.turn_id, observation=receipt(state))

def continued(group):
    first=accepted(started(), final(answer(group,['Original first'])), terminal())
    state=runtime.TurnState(session_id=first.session_id);state.restore_observation(receipt(first))
    root=dict(id='turn_two',session_id=first.session_id,agent_id='agent_two',status='in_progress')
    current=answer('content',['Current answer'],turn='turn_two',identifier='current')
    state.accept(event('created',event_id='second-start',turn_id='turn_two',turn=root))
    state.accept(event('item.done',event_id='second-final',turn_id='turn_two',output_index=0,item=current))
    state.accept(event('completed',event_id='second-end',turn_id='turn_two',turn=dict(root,status='completed')))
    assert state.turn_complete
    return state,current

@pytest.mark.parametrize('group',['content','summary'])
@pytest.mark.parametrize('change',['new_part','new_item','rewrite'])
@pytest.mark.parametrize('pending',[False,True])
def test_prior_get_receipt_keeps_latest_valid_body_and_all_new_facts(group,change,pending):
    state,current=continued(group)
    prior=answer(group,['Canonical first','Newly observed second'] if change=='new_part' else ['Canonical first'])
    values=[prior,current]
    if change=='new_item': values.insert(1,answer(group,['Newly observed second'],identifier='extra'))
    if pending: prior['status']='in_progress'
    observed=recover(state,values)
    assert observed.sync_complete is (not pending)
    records={record['turn_id']:record for record in receipt(observed)['turns']}
    assert 'Canonical first' in repr(records['turn_one']['items'])
    if change!='rewrite': assert 'Newly observed second' in repr(records['turn_one']['items'])
    cropped=recover(observed,[current])
    assert cropped.sync_complete is False and 'Canonical first' in repr(cropped.items)
    if change!='rewrite': assert 'Newly observed second' in repr(cropped.items)
    for value in values: value['status']='completed'
    settled=recover(cropped,values)
    assert settled.sync_complete and 'Canonical first' in repr(settled.items)

@pytest.mark.parametrize('group',['content','summary'])
@pytest.mark.parametrize('pending',[False,True])
def test_newly_discovered_historical_turn_is_retained_without_gating_unrelated_completion(group,pending):
    state=accepted(started(),final(answer('content',['Current answer'])),terminal())
    old=answer(group,['Imported historical body'],turn='older',identifier='older_item')
    if pending:old['status']='in_progress'
    current=answer('content',['Current answer'])
    observed=recover(state,[old,current]);assert observed.sync_complete
    records={record['turn_id']:record for record in receipt(observed)['turns']}
    assert records['older']['root_identity']==[state.session_id,'older','agent_one']
    assert records['older']['terminal_required'] is False
    cropped=recover(observed,[current])
    assert not cropped.sync_complete and 'Imported historical body' in repr(cropped.items)
    restored=recover(cropped,[old,current]);assert restored.sync_complete

@pytest.mark.parametrize('group',['content','summary'])
@pytest.mark.parametrize('conflict',['turn','role','type','part','root'])
def test_prior_get_conflicts_cannot_poison_original_ownership_or_latest_preview(group,conflict):
    state,current=continued(group)
    canonical=answer(group,['Latest canonical','Latest second'])
    observed=recover(state,[canonical,current]);assert observed.sync_complete
    bad=deepcopy(canonical)
    if conflict=='turn':bad['turn_id']='foreign'
    elif conflict=='role':bad['role']='user' if group=='content' else 'assistant'
    elif conflict=='type':bad['type']='function_call'
    elif conflict=='part':bad[group][1]['type']='input_text'
    bad[group][0]['text']='Conflicting text'
    # For reasoning an absent role is not an immutable fact; test a concrete
    # incompatible type instead when exercising the role branch.
    if conflict=='role' and group=='summary':bad['type']='message'
    rejected=recover(observed,[bad,current],wrong_root=conflict=='root')
    assert rejected.sync_complete is False and 'Latest second' in repr(rejected.items)
    known={record['turn_id']:record for record in receipt(rejected)['turns']}
    assert known['turn_one']['root_identity']==[state.session_id,'turn_one','agent_one']
    assert not any(record['turn_id']=='foreign' and any(value['id']=='answer' for value in record['items']) for record in receipt(rejected)['turns'])
    good=recover(rejected,[canonical,current]);assert good.sync_complete


def test_observation_adoption_of_an_active_remote_turn_keeps_its_typed_obligation():
    state=accepted(started(),final(answer('content',['Current answer'])),terminal())
    old=answer('content',['Still running'],turn='older',identifier='older_item');old['status']='in_progress'
    with pytest.raises(runtime.AgentError,match='连接已中断') as caught:
        recover(state,[old,answer('content',['Current answer'])],root_status='in_progress')
    result=caught.value.state
    assert not result.sync_complete
    records={record['turn_id']:record for record in receipt(result)['turns']}
    assert records['older']['terminal_required'] is True


def test_valid_root_without_items_is_captured_before_overlap_events():
    state=runtime.TurnState(session_id='sess_test',turn_id='turn_one')
    client=FakeClient(saved_turn='failed')
    saved=runtime.inspect_saved(client,state.session_id,state.turn_id,include_artifacts=False)
    runtime._apply_saved(client,state,saved)
    assert state.root_identity==('sess_test','turn_one','agent_one')
    assert receipt(state)['turns'][0]['root_identity']==['sess_test','turn_one','agent_one']
    wrong=dict(id='turn_one',session_id='sess_test',agent_id='wrong',status='failed')
    state.accept(event('failed',session_id='sess_test',turn=wrong))
    assert state.root_identity_conflict and not state.turn_complete
