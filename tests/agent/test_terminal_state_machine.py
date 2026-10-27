"""State transitions across item kinds, event order, positions and authoritative reads."""
from copy import deepcopy
import pytest
from modules.agent import runtime
from test_runtime import FakeClient
from test_terminal_integrity import accepted,started,terminal,final,item,reasoning,event

KINDS=['output_text.delta','output_text.done','content_part.added','content_part.done',
       'reasoning_summary_text.delta','reasoning_summary_text.done','reasoning_summary_part.added','reasoning_summary_part.done']

def end(outcome):
    value=terminal();value['type']='agent.session.turn.'+outcome;value['turn']['status']=outcome
    return value

def read(state,items,outcome='completed'):
    client=FakeClient(saved_turn=outcome);client.saved_items=deepcopy(items)
    runtime._reconcile_terminal(client,state)
    return client

def payload(kind,index=0,position=0):
    summary=kind.startswith('reasoning_')
    fields=dict(item_id='reason' if summary else 'answer',output_index=position)
    fields['summary_index' if summary else 'content_index']=index
    if kind.endswith('.delta'):fields['delta']='first'
    elif '_part.' in kind:fields['part']=dict(type='summary_text' if summary else 'output_text',text='first')
    else:fields['text']='first'
    return event(kind,**fields)

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('after_done',[False,True])
@pytest.mark.parametrize('position',[0,1,None,-1,True])
def test_event_position_and_lifecycle_matrix(kind,after_done,position):
    summary=kind.startswith('reasoning_');value=reasoning(['first']) if summary else item(text='first')
    state=accepted(started())
    if summary:state.accept(event('item.added',output_index=0,item=dict(reasoning([]),status='in_progress')))
    if after_done:state.accept(final(value))
    state.accept(payload(kind,position=position))
    if not after_done:state.accept(final(value))
    state.accept(terminal())
    expected=position==0 and type(position) is int and not (after_done and kind.endswith('.delta'))
    assert state.turn_complete is expected
    if expected:assert state.snapshot()['capture']['items']=='partial'
    else:assert state.stream_gap

@pytest.mark.parametrize('kind',KINDS)
def test_new_part_after_done_is_retained_until_complete_get(kind):
    summary=kind.startswith('reasoning_');value=reasoning(['first']) if summary else item(text='first')
    state=accepted(started(),final(value));state.accept(payload(kind,index=1));state.accept(terminal())
    assert not state.turn_complete
    assert len(state.items[value['id']]['summary' if summary else 'content'])==2
    full=deepcopy(value);full['summary' if summary else 'content'].append(dict(type='summary_text' if summary else 'output_text',text='first'))
    read(state,[full]);assert state.sync_complete

@pytest.mark.parametrize('outcome',['completed','failed','cancelled'])
@pytest.mark.parametrize('kind',['message','reasoning','web_search_call','command_execution'])
@pytest.mark.parametrize('status',['completed','incomplete','in_progress','failed','future',None])
def test_stream_and_get_share_type_specific_terminal_contract(outcome,kind,status):
    value=item() if kind=='message' else reasoning(['public']) if kind=='reasoning' else dict(id='tool',type=kind,turn_id='turn_one')
    value['status']=status
    state=accepted(started(),final(value),end(outcome))
    expected=(status=='completed' or kind=='reasoning' and status is None
              or kind=='command_execution' and status=='failed'
              or outcome!='completed' and status=='incomplete')
    assert state.turn_complete is expected
    hydrated=accepted(started());hydrated.accept(end(outcome))
    read(hydrated,[value],outcome)
    assert hydrated.sync_complete is expected

@pytest.mark.parametrize('kind',['reasoning_summary_text.delta','reasoning_summary_part.done'])
def test_summary_limit_is_sparse_and_requires_get_coverage(kind):
    state=accepted(started(),event('item.added',output_index=0,item=dict(reasoning([]),status='in_progress')))
    state.accept(payload(kind,index=100));state.accept(final(reasoning([])));state.accept(terminal())
    assert not state.turn_complete and len(state.items['reason']['summary'])==0
    assert ('summary',100) in state.observed_parts['reason']
    read(state,[reasoning([])]);assert state.sync_complete is False
    full=reasoning(['']*100+['first'])
    read(state,[full]);assert state.sync_complete and len(state.items['reason']['summary'])==101

@pytest.mark.parametrize('kind',['output_text.delta','content_part.done'])
def test_large_content_index_is_recorded_without_allocating_placeholders(kind):
    state=accepted(started());state.accept(payload(kind,index=10**9));state.accept(final(item()));state.accept(terminal())
    assert not state.turn_complete and state.observed_part_count==2
    assert len(state.items['answer']['content'])==1
    read(state,[item()]);assert state.sync_complete is False


def test_get_unfinished_can_later_be_confirmed_without_erasing_known_body():
    state=accepted(started());state.accept(payload('output_text.delta',index=1));state.accept(final(item()));state.accept(terminal())
    full=item();full['content'].append(dict(type='output_text',text='first'));full['status']='in_progress'
    read(state,[full]);assert state.sync_complete is False and len(state.items['answer']['content'])==2
    full['status']='completed';read(state,[full]);assert state.sync_complete


def test_observation_budget_and_unknown_events_do_not_claim_completeness(monkeypatch):
    monkeypatch.setattr(runtime,'MAX_OBSERVED_PARTS',1)
    state=accepted(started());state.accept(payload('output_text.delta'));state.accept(payload('output_text.done',index=1));state.accept(final(item()));state.accept(terminal())
    assert state.unverifiable_stream and not state.turn_complete
    read(state,[item()]);assert state.sync_complete is False
    unknown=accepted(started(),final(item()));unknown.accept(event('future_payload',item_id='answer'));unknown.accept(terminal())
    assert not unknown.turn_complete
    read(unknown,[item()]);assert unknown.sync_complete is False


def test_wrong_get_root_or_known_item_owner_cannot_settle():
    state=accepted(started(),final(item()),terminal())
    client=FakeClient();client.saved_items=[item()]
    client.beta.agents.sessions.turns.retrieve=lambda identifier,**kw:dict(id=identifier,session_id='wrong',agent_id='agent_one',status='completed')
    runtime._reconcile_terminal(client,state);assert state.sync_complete is False
    changed=dict(item(),turn_id='other')
    read(state,[changed,item(identifier='another')]);assert state.sync_complete is False


def test_function_results_are_inputs_and_failed_tool_is_a_settled_output():
    call=dict(id='call',type='function_call',turn_id='turn_one',status='failed')
    result=dict(id='result',type='function_call_output',turn_id='turn_one',status='failed',call_id='c')
    state=accepted(started(),final(call),event('item.done',event_id='input_result',output_index=None,item=result),terminal())
    assert state.turn_complete


def test_get_checks_current_turn_only_and_reasoning_private_content_is_not_public():
    public=dict(reasoning(['visible']),content='PRIVATE',encrypted_content='HIDDEN')
    state=accepted(started(),final(public),terminal());assert state.turn_complete
    read(state,[dict(item(identifier='old'),turn_id='older',status='in_progress'),public]);assert state.sync_complete


@pytest.mark.parametrize('field,value',[('id',''),('role','future'),('status','future')])
def test_unknown_identity_role_or_status_never_makes_stream_or_get_ready(field,value):
    record=item();record[field]=value
    state=accepted(started(),final(record),terminal());assert not state.turn_complete
    read(state,[record]);assert state.sync_complete is False


def test_nonterminal_session_read_does_not_clear_uncertainty():
    state=accepted(started(),final(item()),terminal())
    client=FakeClient(session_status='in_progress');client.saved_items=[item()]
    runtime._reconcile_terminal(client,state);assert state.sync_complete is False


def test_changed_same_shape_snapshot_is_not_silently_ignored():
    state=accepted(started(),final(item(text='first')))
    state.accept(event('item.updated',event_id='changed',output_index=0,item=item(text='updated')));state.accept(terminal())
    assert not state.turn_complete and state.text=='updated'
    read(state,[item(text='updated')]);assert state.sync_complete and state.text=='updated'
