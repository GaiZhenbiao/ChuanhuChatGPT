"""Invisible canonical records do not split visible tools or corrupt body copy."""
from base64 import b64decode
from copy import deepcopy
import json
import re
import pytest
from agent_fixtures import env
from test_realtime_activity import model_for_stream, accept, rendered, item_event
from test_runtime import message, turn
from test_two_layer_activity import command, timeline
from modules.agent import runtime
from modules.agent.activity import group_span, persist_group_durations
from modules.agent.transcript_view import _tool_runs
from modules.agent.message_files import decode_rows


def reasoning(status='in_progress'):
    return dict(id='r',type='reasoning',turn_id='t1',status=status,summary=[])


def tool_groups(entries, **kwargs):
    return [entry for entry in _tool_runs(entries, 'scope', **kwargs) if entry['kind'] == 'tool_group']


@pytest.mark.parametrize('separator', [message('empty', ''), message('blank', ' \n '), reasoning('completed'), reasoning('failed')])
def test_invisible_records_bridge_and_first_group_anchor_stays_stable(separator):
    entries=timeline([message('u','question',role='user'),command('a'),separator,command('b')])
    original=deepcopy(entries)
    groups=tool_groups(entries)
    assert len(groups)==1 and len(groups[0]['entries'])==2
    assert groups[0]['id']==tool_groups(entries[:2])[0]['id']
    assert entries==original
    assert any(entry['id']==entries[2]['id'] for entry in _tool_runs(entries,'scope'))


def test_live_thinking_only_splits_its_active_turn_and_completed_empty_rejoins():
    entries=timeline([command('a'),reasoning(),command('b')]);ref=entries[0]['turn_ref']
    assert len(tool_groups(entries,active_turn=ref))==2
    assert len(tool_groups(entries,active_turn='another-turn'))==1
    assert len(tool_groups(entries,active_turn=ref,clock={'r':{'phase':'completed'}}))==1


@pytest.mark.parametrize('change', ['text','summary','warning','file','media','unsupported','turn'])
def test_visible_and_uncertain_boundaries_are_preserved(change):
    entries=timeline([command('a'),message('middle',''),command('b')]);middle=entries[1]
    if change=='text':middle['content']=[{'type':'text','text':'visible'}]
    elif change=='summary':middle.update(kind='summary',content=[{'type':'summary_text','text':'public'}])
    elif change=='warning':middle['capture']['omitted']=True
    elif change=='file':middle['file_refs']=['file']
    elif change=='media':middle['content']=[{'type':'image'}]
    elif change=='unsupported':middle['kind']='unsupported'
    elif change=='turn':middle['turn_ref']='other-turn'
    assert len(tool_groups(entries))==2
    if change!='turn':assert tool_groups(entries)[0]['id']!=tool_groups(entries)[1]['id']


def test_unknown_turn_never_proves_two_tools_are_consecutive_in_one_turn():
    entries=timeline([command('a'),command('b')])
    for entry in entries:entry['turn_ref']=None
    assert len(tool_groups(entries))==2


def test_merged_duration_is_full_wall_span_and_not_sum():
    entries=timeline([command('a'),reasoning('completed'),command('b')])
    for entry,start,end in [(entries[0],0,300),(entries[2],200,500)]:
        entry['activity_interval']=dict(clock_id='a'*32,started_ms=start,ended_ms=end,sampled_ms=500)
    groups=tool_groups(entries)
    assert group_span(groups[0])=={'elapsed_ms':500,'running':False}
    persist_group_durations(entries)
    assert entries[0]['tool_group_duration']['members']==[entries[0]['id'],entries[2]['id']]
    assert entries[0]['tool_group_duration']['elapsed_ms']==500


def copied_body(markup):
    payloads=[json.loads(b64decode(value)) for value in re.findall('data-agent-body-raw="([^"]+)"',markup)]
    return '\n\n'.join(part['raw'] for part in sorted(payloads,key=lambda part:part['position']))


@pytest.mark.parametrize('separator',['',' \n '])
def test_real_stream_empty_assistant_preserves_order_body_copy_and_saved_projection(env,separator):
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(message('u','question',role='user'),None))
    items=[message('intro','INTRO'),command('a','echo FIRST'),message('empty',separator),
           reasoning('completed'),command('b','echo SECOND'),message('answer','FINAL')]
    for index,item in enumerate(items):state.accept(item_event(item,index))
    model=model_for_stream(env);accept(model,state)
    for terminal in (False,True):
        if terminal:
            state.accept(turn('completed'));accept(model,state)
            model._sync_items(state.snapshot()['items'])
        output=rendered(model);body=output[0][1]
        assert body.count('agent-history-group')==1
        assert 'data-body-before="true"' in body and 'data-body-after="true"' in body
        assert body.index('md-message">INTRO')<body.index('echo FIRST</span>')<body.index('echo SECOND</span>')<body.index('md-message">FINAL')
        assert decode_rows(output,model._conversation_id)==model._display
        assert copied_body(body)==model._display[0][1]
