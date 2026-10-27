"""Known web enums share one outer category; real child actions remain intact."""
from copy import deepcopy
import html
import re
import pytest
from agent_fixtures import env
from test_two_layer_activity import groups, command
from test_combined_activity_titles import web
from modules.agent.transcript_view import _group_action, _group_title, _tool_group
from modules.presets import i18n


@pytest.fixture(autouse=True)
def chinese_titles():
    previous=i18n.language;i18n.change_language('zh_CN')
    yield
    i18n.change_language(previous)


@pytest.mark.parametrize('items,expected',[
    ([web('s','search'),web('o','open_page'),command('c'),web('f','find_in_page')],'正在搜索网页和运行命令'),
    ([web('o','open_page'),command('c'),web('s','search'),web('f','find_in_page')],'正在搜索网页和运行命令'),
    ([command('c'),web('f','find_in_page'),web('s','search'),web('o','open_page')],'正在运行命令和搜索网页'),
    ([web('o','open_page'),web('f','find_in_page'),web('o2','open_page'),web('s','search')],'正在搜索网页'),
])
def test_outer_deduplicates_known_web_category_in_first_seen_order(items,expected):
    group=groups(items)[0];before=deepcopy(group)
    assert _group_title(group['entries'])==expected
    markup=_tool_group(group,scope='scope',conversation='chat')
    assert markup.count('data-layer="tool"')==len(items) and group==before


def test_inner_summaries_and_all_raw_actions_remain_real_and_separate():
    group=groups([web('s','search'),web('o','open_page'),command('c'),web('f','find_in_page')])[0]
    markup=_tool_group(group,scope='scope',conversation='chat')
    assert _group_title(group['entries'])=='正在搜索网页和运行命令'
    summaries=re.findall(r'<summary[^>]*>(.*?)</summary>',markup)
    assert '>网页搜索</span>' in summaries[1] and '>打开网页</span>' in summaries[2] and '>页内查找</span>' in summaries[4]
    raw=html.unescape(markup)
    for action in ('search','open_page','find_in_page'):assert '"type": "'+action+'"' in raw
    assert markup.count('data-layer="tool"')==4


@pytest.mark.parametrize('action',['open_page','find_in_page'])
@pytest.mark.parametrize('status,expected',[('failed','搜索网页和运行命令'),('cancelled','搜索网页和运行命令'),('unknown_future_status','正在搜索网页和运行命令'),('in_progress','正在搜索网页和运行命令'),('completed','搜索了网页和运行了命令')])
def test_merged_web_item_still_controls_whole_group_success_and_tense(action,status,expected):
    items=[web('s','search','completed'),dict(command('c'),status='completed',exit_code=0),web('last',action,status)]
    entries=groups(items)[0]['entries']
    clock={entry['source_id']:dict(phase='completed') for entry in entries}
    assert _group_title(entries,clock)==expected


@pytest.mark.parametrize('action',[None,'other','read_file','Search','open_page_future'])
def test_unknown_web_enums_keep_generic_mapping_even_if_text_mentions_known_actions(action):
    item=web('unknown',action)
    item['action']['query']='search open_page find_in_page'
    item['output']='search open_page find_in_page'
    entry=groups([item])[0]['entries'][0]
    assert _group_action(entry)=='web_search_call'
    assert _group_title([entry])=='网页操作'
    entries=groups([web('known','search'),item])[0]['entries']
    assert [_group_action(entry) for entry in entries]==['web_search','web_search_call']


@pytest.mark.parametrize('kind',['function_call','function_call_output','mcp_call','computer_use_call','create_subagent_call','send_subagent_input_call','resume_subagent_call','wait_for_subagents_call','interrupt_subagent_call','close_subagent_call','agent_message'])
def test_other_source_types_keep_original_separate_mapping(kind):
    entry=dict(source_type=kind,details={'name':'web_search','command':'find_in_page','action':{'type':'open_page'}})
    assert _group_action(entry)==kind


def test_unknown_web_actual_type_is_not_guessed_from_tool_name_or_shell():
    assert _group_action(dict(source_type='future_tool',details={'name':'web_search','command':'search open_page'}))=='other'
    assert _group_action(dict(source_type='command_execution',details={'command':'open_page find_in_page search'}))=='command_execution'
