"""Approved outer title composition leaves grouping and task/display state intact."""
from copy import deepcopy
import html
import json
import re
from pathlib import Path
import pytest
from agent_fixtures import env
from test_runtime import message, turn
from test_realtime_activity import model_for_stream, accept, rendered, item_event, reasoning
from test_two_layer_activity import command, groups, timeline
from modules.agent import runtime
from modules.agent.transcript_view import _group_title, _tool_group, _tool_runs
from modules.presets import i18n


@pytest.fixture(autouse=True)
def chinese_titles():
    previous=i18n.language
    i18n.change_language('zh_CN')
    yield
    i18n.change_language(previous)


def web(key='w',action='search',status='in_progress'):
    return dict(id=key,turn_id='t1',type='web_search_call',status=status,action={'type':action})


def test_mixed_actions_stay_in_one_group_deduplicated_in_first_seen_order_without_counts():
    items=[web(),command('a'),dict(id='f',turn_id='t1',type='function_call',name='actual',call_id='f'),command('b'),web('w2')]
    result=groups(items)
    assert len(result)==1 and len(result[0]['entries'])==5
    title=_group_title(result[0]['entries'])
    assert title=='正在搜索网页、运行命令和调用函数'
    assert title.count('正在')==1 and not any(char.isdigit() for char in title)
    assert _group_title(groups([command('a'),web(),command('b'),web('w2')])[0]['entries'])=='正在运行命令和搜索网页'
    assert _group_title(groups([web(),web('w2')])[0]['entries'])=='正在搜索网页'


def test_web_actions_share_outer_category_but_keep_the_existing_single_mixed_group():
    result=groups([web('s','search'),web('o','open_page'),web('f','find_in_page'),web('s2','search')])
    assert len(result)==1
    assert _group_title(result[0]['entries'])=='正在搜索网页'


@pytest.mark.parametrize('status', ['unknown_future_status',None,'in_progress'])
def test_unknown_missing_and_running_actual_status_keep_progressive_even_with_completed_clock(status):
    entries=groups([dict(command('a'),status=status,exit_code=0),web()])[0]['entries']
    before=deepcopy(entries);clock={'a':dict(phase='completed',elapsed_ms=3000,running=False)};saved=deepcopy(clock)
    assert _group_title(entries,clock)=='正在运行命令和搜索网页'
    assert entries==before and clock==saved,'title must not mutate phase or elapsed/freeze metadata'


def test_unconfirmed_local_phase_is_progressive_without_inventing_running_clock():
    entries=groups([command('a'),web()])[0]['entries']
    clock={'a':dict(phase='incomplete',elapsed_ms=1000,running=False),'w':dict(phase='incomplete',elapsed_ms=2000,running=False)}
    assert _group_title(entries,clock)=='正在运行命令和搜索网页'
    assert not clock['a']['running'] and not clock['w']['running']


@pytest.mark.parametrize('status', ['failed','cancelled','incomplete','requires_action'])
def test_explicit_failure_stop_or_user_action_keeps_neutral_mixed_title(status):
    entries=groups([dict(command('a'),status=status),web()])[0]['entries']
    assert _group_title(entries)=='运行命令和搜索网页'


@pytest.mark.parametrize('phase', ['failed','cancelled','turn_failed','turn_cancelled','requires_action'])
def test_explicit_observed_failure_or_stop_keeps_neutral_title(phase):
    entries=groups([command('a'),web()])[0]['entries']
    assert _group_title(entries,{'a':dict(phase=phase)})=='运行命令和搜索网页'


def test_finished_unsuccessful_command_does_not_claim_to_be_still_running():
    for exit_code in (1,None):
        entries=groups([dict(command('a'),status='completed',exit_code=exit_code),web()])[0]['entries']
        assert _group_title(entries)=='运行命令和搜索网页'


def test_waiting_function_result_is_progressive_but_actual_failure_or_approval_is_neutral():
    function=dict(id='f',turn_id='t1',type='function_call',status='completed',name='actual',call_id='call')
    entries=groups([function,web()])[0]['entries']
    assert _group_title(entries)=='正在调用函数和搜索网页'
    assert _group_title(entries,{'f':dict(phase='waiting')})=='正在调用函数和搜索网页'
    failed=timeline([dict(id='r',turn_id='t1',type='function_call_output',call_id='call',output='',error='real error')])[0]
    assert _group_title(entries,outputs={(failed['turn_ref'],'call'):failed})=='调用函数和搜索网页'
    approval=dict(id='auth',turn_id='t1',type='computer_use_approval_request',status='in_progress')
    assert _group_title(groups([command('a'),approval])[0]['entries'])=='运行命令和网站授权请求'


def test_every_execution_result_must_be_confirmed_before_mixed_past_title():
    done=dict(command('a'),status='completed',exit_code=0)
    function=dict(id='f',turn_id='t1',type='function_call',status='completed',name='actual',call_id='call')
    entries=groups([done,web(status='completed'),function])[0]['entries']
    assert _group_title(entries)=='正在运行命令、搜索网页和调用函数'
    result=timeline([dict(id='r',turn_id='t1',type='function_call_output',call_id='call',output='real result')])[0]
    assert _group_title(entries,outputs={(result['turn_ref'],'call'):result})=='运行了命令、搜索了网页和调用了函数'
    assert _group_title(groups([done,web(status='completed')])[0]['entries'])=='运行了命令和搜索了网页'


def test_title_changes_leave_group_identity_inner_markup_and_open_defaults_intact():
    items=[command('a'),web()];original=groups(items)[0]
    done=groups([dict(items[0],status='completed',exit_code=0),dict(items[1],status='completed')])[0]
    assert done['id']==original['id'] and done['persist_open']==original['persist_open']
    assert [entry['id'] for entry in done['entries']]==[entry['id'] for entry in original['entries']]
    output=_tool_group(original,scope='scope',conversation='chat')
    assert output.count('<details ')==3 and ' open' not in output
    assert 'data-layer="group" data-persist-open="true"' in output
    assert 'pwd</span>' in output and '网页搜索</span>' in output
    assert '&quot;type&quot;: &quot;command_execution&quot;' in output and '&quot;type&quot;: &quot;web_search_call&quot;' in output
    assert original['id'] in output


def test_special_tool_names_are_not_outer_actions_and_are_escaped_inside():
    name='<script>alert("unsafe")</script>'
    items=[dict(id='f',turn_id='t1',type='function_call',name=name,call_id='f'),dict(command('a'),command=name)]
    group=groups(items)[0];output=_tool_group(group,scope='scope',conversation='chat')
    assert _group_title(group['entries'])=='正在调用函数和运行命令'
    assert '<script>' not in output and html.escape(name) in output


def test_unknown_web_action_keeps_type_fallback_and_unknown_native_payload_stays_unsupported():
    group=groups([web(action='unknown_future_action')])[0]
    assert _group_title(group['entries'])=='网页操作'
    result=_tool_runs(timeline([command('a'),dict(id='x',turn_id='t1',type='unknown_native_tool',output='UNSAFE_RAW_PAYLOAD'),web()]),'scope')
    assert [entry['kind'] for entry in result]==['tool_group','unsupported','tool_group']
    assert 'UNSAFE_RAW_PAYLOAD' not in repr(result)


def test_real_projection_keeps_body_summary_boundaries_copy_and_mixed_group_order(env):
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(message('u','question',role='user'),None))
    state.accept(item_event(command('a'),0));state.accept(item_event(web(),1))
    state.accept(item_event(reasoning('completed','PUBLIC SUMMARY'),2))
    state.accept(item_event(command('b'),3));state.accept(item_event(web('w2'),4))
    state.accept(item_event(message('comment','COMMENTARY'),5));state.accept(item_event(command('c'),6))
    state.accept(item_event(message('final','FINAL'),7,'done'))
    model=model_for_stream(env);accept(model,state);body=rendered(model)[0][1]
    assert body.count('agent-history-group')==3
    assert body.count('正在运行命令和搜索网页')==4 # visible title and aria-label for two groups
    assert body.index('PUBLIC SUMMARY')<body.index('md-message">COMMENTARY')<body.index('md-message">FINAL')
    assert 'raw-message hideM' in body


@pytest.mark.parametrize('language', sorted(path.stem for path in Path('locale').glob('*.json')))
def test_supported_languages_use_localized_or_existing_english_fallback_natural_lists(language):
    i18n.change_language(language)
    entries=groups([command('a'),web(),dict(id='f',turn_id='t1',type='function_call',name='actual',call_id='f')])[0]['entries']
    title=_group_title(entries)
    expected='正在运行命令、搜索网页和调用函数' if language=='zh_CN' else 'Running commands, searching the web, and calling functions'
    assert title==expected
    if language!='zh_CN':assert '和' not in title and 'ui.agent_activity' not in title
    assert len(json.loads(Path('locale',language+'.json').read_text())['ui']['toolbox']['agent'])==32
