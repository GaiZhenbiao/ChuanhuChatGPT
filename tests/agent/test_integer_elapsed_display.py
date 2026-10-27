"""Only group headers display floored, localized observation duration."""
from copy import deepcopy
import pytest
from modules.agent import transcript
from modules.agent.transcript_view import _activity, _tool_runs, _tool_group, i18n


def entry(**extra):
    return transcript.normalize([dict(id='cmd',type='command_execution',turn_id='t1',status='in_progress',command='pwd',**extra)],scope_id='scope')['timeline'][0]


def group():
    return _tool_runs([entry()], 'scope')[0]


def observation(elapsed, running=False):
    return {'cmd': dict(phase='running' if running else 'completed', elapsed_ms=elapsed,
        running=running, interval=dict(clock_id='a'*32, started_ms=0,
        ended_ms=None if running else elapsed, sampled_ms=elapsed))}


@pytest.mark.parametrize('elapsed,expected',[(0,'0.0s'),(.1,'0.1s'),(10,'0.1s'),(100,'0.1s'),(999,'0.9s'),(999.75,'0.9s'),(1000,'1s'),(1000.1,'1s'),(1999.9,'1s'),(2000,'2s'),(59999.9,'59s'),(60000,'1分0秒'),(67999.9,'1分7秒')])
def test_group_floors_seconds_keeps_precision_and_child_has_no_timer(elapsed,expected):
    previous=i18n.language
    i18n.change_language('zh_CN')
    try:
        clock=observation(elapsed);saved=deepcopy(clock)
        markup=_tool_group(group(),scope='scope',conversation='chat',clock=clock,active=True)
        assert f'data-elapsed-ms="{elapsed}"' in markup and f'>{expected}</span>' in markup
        assert markup.count('agent-activity-elapsed')==1
        assert 'agent-activity-elapsed' not in _activity([entry()],clock=clock,active=True)
        assert clock==saved
    finally:i18n.change_language(previous)


@pytest.mark.parametrize('elapsed',[None,-1,float('nan'),float('inf'),31536000001,False])
def test_group_omits_unreliable_values_instead_of_inventing_zero(elapsed):
    assert 'agent-activity-elapsed' not in _tool_group(group(),scope='scope',conversation='chat',clock=observation(elapsed),active=True)


@pytest.mark.parametrize('phase',['completed','failed','turn_failed','cancelled','turn_cancelled','incomplete'])
def test_terminal_group_freezes_while_child_remains_without_timer(phase):
    clock=observation(999.75);clock['cmd']['phase']=phase
    markup=_tool_group(group(),scope='scope',conversation='chat',clock=clock,active=True)
    assert '>0.9s</span>' in markup and 'data-running="false"' in markup and 'data-elapsed-ms="999.75"' in markup


def test_native_duration_is_preserved_but_cannot_substitute_for_group_interval():
    item=entry(duration_ms=999.75)
    assert item['details']['duration_ms']==999.75
    markup=_tool_group(_tool_runs([item],'scope')[0],scope='scope',conversation='chat',clock={'cmd':dict(phase='completed',elapsed_ms=2000,running=False)})
    assert 'agent-activity-elapsed' not in markup


def test_live_group_uses_sender_interval_without_cross_process_monotonic_arithmetic():
    clock=observation(999.75,running=True)
    clock['cmd']['sampled_at']=10**18
    markup=_tool_group(group(),scope='scope',conversation='chat',clock=clock,active=True)
    assert 'data-running="true"' in markup and '>0.9s</span>' in markup
    assert 'agent-activity-elapsed' not in _tool_group(group(),scope='scope',conversation='chat',clock=clock,active=False)
