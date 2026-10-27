"""Keep every action in semantic titles; only CSS may truncate their visual width."""
from copy import deepcopy
import html
import pytest
from agent_fixtures import env
from test_two_layer_activity import groups, command
from test_combined_activity_titles import web
from modules.agent.transcript_view import _group_title, _tool_group
from modules.presets import i18n


@pytest.fixture(autouse=True)
def chinese_titles():
    previous=i18n.language;i18n.change_language('zh_CN')
    yield
    i18n.change_language(previous)


def actions():
    return [command('c'),web('s','search'),web('o','open_page'),web('find','find_in_page'),
            dict(id='fn',type='function_call',turn_id='t1',status='in_progress',name='actual_function',call_id='call'),
            dict(id='mcp',type='mcp_call',turn_id='t1',status='in_progress',name='actual_mcp'),
            dict(id='computer',type='computer_use_call',turn_id='t1',status='in_progress')]


@pytest.mark.parametrize('count',[3,4,7])
def test_title_keeps_every_distinct_category_and_preserves_every_child(count):
    group=groups(actions()[:count])[0];before=deepcopy(group)
    title=_group_title(group['entries'])
    expected={3:'正在运行命令和搜索网页',4:'正在运行命令和搜索网页',7:'正在运行命令、搜索网页、调用函数、调用工具和操作计算机'}
    assert title==expected[count] and '…' not in title
    markup=_tool_group(group,scope='scope',conversation='conversation')
    assert markup.count('data-layer="tool"')==count
    assert group==before
    assert '工具操作（' not in title and '等工具' not in title and not any(x.isdigit() for x in title)
    if count==7:
        assert 'actual_function' in markup and 'actual_mcp' in markup
        assert 'function_call' in html.unescape(markup) and 'computer_use_call' in html.unescape(markup)


def test_all_actions_keep_first_seen_deduplication_order():
    group=groups([web('s'),command('c'),web('s2'),command('c2'),web('o','open_page'),web('find','find_in_page')])[0]
    assert _group_title(group['entries'])=='正在搜索网页和运行命令'
    assert len(group['entries'])==6
    assert _group_title(groups([web('s'),command('c'),web('s2'),command('c2')])[0]['entries'])=='正在搜索网页和运行命令'


@pytest.mark.parametrize('status,expected',[('failed','运行命令和搜索网页'),('unknown_future_status','正在运行命令和搜索网页'),('in_progress','正在运行命令和搜索网页'),('completed','运行了命令和搜索了网页')])
def test_fourth_action_still_decides_whole_group_tense(status,expected):
    items=actions()[:4]
    items[0].update(status='completed',exit_code=0)
    items[1]['status']=items[2]['status']='completed';items[3]['status']=status
    entries=groups(items)[0]['entries']
    clock={entry['source_id']:dict(phase='completed') for entry in entries}
    assert _group_title(entries,clock)==expected


def test_unlisted_fourth_repeated_action_failure_is_not_ignored():
    items=[dict(command('c'),status='completed',exit_code=0),web('s',status='completed'),web('o','open_page',status='completed'),dict(command('c2'),status='failed')]
    assert _group_title(groups(items)[0]['entries'])=='运行命令和搜索网页'


def test_shell_contents_do_not_invent_read_action_and_full_raw_command_survives():
    text='cat '+('very-long-path/'*30)+'secret-free-file.txt'
    group=groups([command('c',text),web('s')])[0]
    assert _group_title(group['entries'])=='正在运行命令和搜索网页'
    markup=_tool_group(group,scope='scope',conversation='conversation')
    assert text in html.unescape(markup)
    assert 'agent-command-preview' in markup and '读取' not in _group_title(group['entries'])


def test_english_long_title_keeps_all_five_categories_and_seven_children_without_manual_ellipsis():
    i18n.change_language('en_US');group=groups(actions())[0]
    title=_group_title(group['entries'])
    assert '…' not in title and '...' not in title
    assert title=='Running commands, searching the web, calling functions, calling tools, and using the computer'
    assert len(group['entries'])==7
