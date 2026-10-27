"""UE-defined contiguous tool groups and stable display-only expansion identities."""
from copy import deepcopy
import html
import re
import pytest
from agent_fixtures import env
from test_runtime import message, turn
from test_realtime_activity import model_for_stream, accept, rendered, item_event, reasoning
from modules.agent import runtime, transcript
from modules.agent.transcript_view import _tool_runs, _tool_group, _confirmed_execution
from modules.agent.message_files import decode_rows
from modules.presets import i18n


@pytest.fixture(autouse=True)
def chinese_group_titles():
    previous=i18n.language
    i18n.change_language('zh_CN')
    yield
    i18n.change_language(previous)


def command(key, text='pwd', turn_id='t1'):
    return dict(id=key,type='command_execution',turn_id=turn_id,status='in_progress',command=text)


def timeline(items):
    return transcript.normalize(items,scope_id='scope')['timeline']


def groups(items):
    return [entry for entry in _tool_runs(timeline(items),'scope') if entry['kind']=='tool_group']


def test_anchor_is_previous_occurrence_and_stable_under_tool_insert_append_and_split():
    user=message('u','question',role='user');a=command('a');b=command('b');c=command('c')
    original=groups([user,a,b])[0]
    assert original['persist_open']
    assert groups([user,c,a,b])[0]['id']==original['id']
    assert groups([user,a,b,c])[0]['id']==original['id']
    split=groups([user,a,message('comment','commentary'),b])
    assert len(split)==2 and split[0]['id']==original['id'] and split[1]['id']!=original['id']
    assert split[1]['entries'][0]['id']==original['entries'][1]['id']
    assert groups([a])[0]['id']==groups([b,a])[0]['id'] # stable turn-start, not first tool
    assert groups([command('a',turn_id='other')])[0]['id']!=groups([a])[0]['id']


def test_public_summary_unsupported_and_turn_change_break_runs():
    items=[command('a'),reasoning('completed','public'),command('b'),dict(id='x',turn_id='t1',type='unsupported_test'),command('c'),command('d',turn_id='other')]
    result=_tool_runs(timeline(items),'scope')
    assert [entry['kind'] for entry in result]==['tool_group','summary','tool_group','unsupported','tool_group','tool_group']
    assert all(len(entry['entries'])==1 for entry in result if entry['kind']=='tool_group')


def test_unresolved_boundary_and_tool_disable_only_unsafe_expansion_memory():
    stable=command('a');unknown=command(None)
    group=groups([stable,unknown])[0]
    assert not group['persist_open']
    output=_tool_group(group,scope='scope',conversation='chat')
    assert 'data-layer="group" data-persist-open="false"' in output
    assert 'data-layer="tool" data-persist-open="true"' in output
    assert 'data-activity-key=""' in output and 'data-layer="tool" data-persist-open="false"' in output
    boundary=groups([message(None,'unresolved boundary'),stable])[0]
    assert boundary['id']=='' and not boundary['persist_open']
    assert 'data-layer="tool" data-persist-open="true"' in _tool_group(boundary,scope='scope',conversation='chat')


def test_two_layers_real_command_default_closed_no_group_duration_or_badges():
    group=groups([command('a','python -c "print(1)"')])[0]
    output=_tool_group(group,scope='scope',conversation='chat',clock={'a':dict(phase='running',elapsed_ms=2000,running=True,sampled_at=0)},active=False)
    assert output.count('<details ')==2 and ' open' not in output
    assert 'agent-history-group' in output and 'agent-command-preview' in output
    assert '正在运行命令</span>' in output and 'python -c' in output
    outer=re.search('<summary[^>]*>(.*?)</summary>',output).group(1)
    assert 'elapsed' not in outer and 'badge' not in output
    assert 'agent-activity-elapsed' not in output  # Legacy elapsed-only data cannot prove a group interval.
    assert output.count('aria-hidden="true"')==2 and 'fill="none"' in output
    assert '&quot;type&quot;: &quot;command_execution&quot;' in output
    mixed=groups([command('a'),dict(id='w',turn_id='t1',type='web_search_call',action={'type':'search'},status='completed')])[0]
    assert '>正在运行命令和搜索网页</span>' in _tool_group(mixed,scope='scope',conversation='chat')
    no_command=groups([dict(command('empty'),command='')])[0]
    assert '>正在运行命令</span>' in _tool_group(no_command,scope='scope',conversation='chat')
    assert _tool_group(no_command,scope='scope',conversation='chat').count('>命令执行</span>')==1


def test_group_action_uses_native_type_and_web_action_never_command_or_free_name():
    def outer(items):
        output=_tool_group(groups(items)[0],scope='scope',conversation='chat')
        return re.search('<summary[^>]*>(.*?)</summary>',output).group(1)
    for status in ('in_progress','completed','failed','incomplete'):
        label='正在运行命令' if status=='in_progress' else '运行命令'
        assert '>'+label+'</span>' in outer([dict(command('a','cat read_file.txt'),status=status)])
    for action,label in [('search','搜索网页'),('open_page','搜索网页'),('find_in_page','搜索网页'),('other','网页操作'),('read_file','网页操作')]:
        label='正在'+label if action in ('search','open_page','find_in_page') else label
        assert '>'+label+'</span>' in outer([dict(id='w',turn_id='t1',type='web_search_call',status='in_progress',action={'type':action})])
    assert '>正在调用函数</span>' in outer([dict(id='f',turn_id='t1',type='function_call',name='read_file',call_id='f',arguments={})])
    assert '>正在调用工具</span>' in outer([dict(id='m',turn_id='t1',type='mcp_call',name='read_file',server_label='files',arguments={})])
    assert '>正在搜索网页</span>' in outer([dict(id='w1',turn_id='t1',type='web_search_call',action={'type':'search'}),dict(id='w2',turn_id='t1',type='web_search_call',action={'type':'open_page'})])


def test_past_action_requires_every_execution_result_and_no_pending_call_output():
    def outer(items,**kwargs):
        output=_tool_group(groups(items)[0],scope='scope',conversation='chat',**kwargs)
        return re.search('<summary[^>]*>(.*?)</summary>',output).group(1)
    done=dict(command('a'),status='completed',exit_code=0,output='')
    assert '>运行了命令</span>' in outer([done,dict(done,id='b')])
    for status in ('in_progress','failed','incomplete','cancelled'):
        label='正在运行命令' if status=='in_progress' else '运行命令'
        assert '>'+label+'</span>' in outer([done,dict(done,id='b',status=status)])
    assert '>运行命令</span>' in outer([dict(done,exit_code=1)])
    assert '>运行命令</span>' in outer([dict(done,exit_code=None)])
    assert '>正在运行命令</span>' in outer([dict(done,status='in_progress')],clock={'a':dict(phase='completed')})
    function=dict(id='f',turn_id='t1',type='function_call',status='completed',name='read_file',call_id='call',arguments={})
    assert '>正在调用函数</span>' in outer([function])
    assert '>正在调用函数</span>' in outer([function],clock={'f':dict(phase='completed')})
    result=timeline([dict(id='r',turn_id='t1',type='function_call_output',call_id='call',output='real result')])[0]
    assert '>调用了函数</span>' in outer([function],outputs={(result['turn_ref'],'call'):result})
    assert '>调用函数</span>' in outer([function],outputs={(result['turn_ref'],'call'):result},clock={'f':dict(phase='waiting')})
    result['status']='in_progress'
    assert '>正在调用函数</span>' in outer([function],outputs={(result['turn_ref'],'call'):result})
    result.pop('status')
    result['details']['error']='actual failure'
    assert '>调用函数</span>' in outer([function],outputs={(result['turn_ref'],'call'):result})
    mcp=dict(id='m',turn_id='t1',type='mcp_call',status='completed',name='read_file',arguments={})
    assert '>调用工具</span>' in outer([mcp])
    assert '>调用了工具</span>' in outer([dict(mcp,output='real result')])
    web=dict(id='w',turn_id='t1',type='web_search_call',status='completed',action={'type':'search'})
    assert '>搜索了网页</span>' in outer([web])
    assert '>运行了命令和搜索了网页</span>' in outer([done,web])


def test_unknown_or_missing_execution_status_cannot_be_promoted_by_observation_clock():
    for kind,details in [('command_execution',dict(command='pwd',exit_code=0)),('mcp_call',dict(name='f',output='result')),
                         ('function_call',dict(name='f',call_id='call')),('web_search_call',dict(action={'type':'search'})),
                         ('computer_use_call',dict(title='real activity'))]:
        for status in (None,'unknown_future_status','in_progress','failed','incomplete','cancelled'):
            entry=timeline([dict(id='item',turn_id='t1',type=kind,status=status,**details)])[0]
            assert not _confirmed_execution(entry,{'item':dict(phase='completed')},{})
    # The SDK function result has no required status. Its compatibility is
    # explicit and cannot be extended to unknown future status values.
    result=timeline([dict(id='result',turn_id='t1',type='function_call_output',call_id='call',output='result')])[0]
    assert _confirmed_execution(result,{'result':dict(phase='completed')},{})
    result['status']='unknown_future_status'
    assert not _confirmed_execution(result,{'result':dict(phase='completed')},{})


def test_real_projection_preserves_commentary_order_copy_decode_and_group_identity(env):
    state=runtime.TurnState();state.accept(turn('created'))
    state.accept(item_event(message('u','question',role='user'),None))
    state.accept(item_event(command('a'),0));state.accept(item_event(command('b'),1))
    model=model_for_stream(env);accept(model,state)
    before=rendered(model)[0][1]
    anchor=re.search('agent-history-group" data-activity-key="([^"]+)"',before).group(1)
    state.accept(item_event(message('comment','COMMENTARY'),2))
    state.accept(item_event(command('c','echo c'),3))
    state.accept(item_event(message('final','FINAL'),4,'done'))
    accept(model,state);output=rendered(model);body=output[0][1]
    assert body.count('agent-history-group')==2
    assert anchor in body
    assert body.index('pwd</span>')<body.index('md-message">COMMENTARY')<body.index('echo c</span>')<body.index('md-message">FINAL')
    assert decode_rows(output,model._conversation_id)==model._display
    raw='\n\n'.join(re.findall(r'<div class="raw-message hideM">(.*?)</div>',body,re.S))
    assert html.unescape(raw)=='COMMENTARY\n\nFINAL'
