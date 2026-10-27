import logging
from types import SimpleNamespace
import pytest
from modules.agent.tool_logging import ToolLog, safe_text
from agent_fixtures import env, select, send
from test_runtime import message


def records(caplog):
    return [r.getMessage() for r in caplog.records if r.msg == '%s']


def items():
    return [dict(id='call', type='function_call', call_id='c', name='count_words', turn_id='t1', status='completed'),
            dict(id='result', type='function_call_output', call_id='c', output=[{'type':'input_text','text':'words=3'}, {'type':'input_image','image_url':'data:BASE64_PRIVATE'}], error=None, turn_id='t1', status='completed'),
            dict(id='cmd', type='command_execution', command='python report.py', output='created report.pdf', exit_code=0, duration_ms=12, turn_id='t1', status='completed'),
            dict(id='mcp', type='mcp_call', name='read', server_label='docs', output={'text':'read complete','authorization':'NEVER'}, turn_id='t1', status='completed'),
            dict(id='search', type='web_search_call', action={'type':'search','query':'private query'}, turn_id='t1', status='completed')]


def test_tools_final_history_names_outputs_and_recovery_dedup(caplog):
    caplog.set_level(logging.INFO)
    model=SimpleNamespace(_state={'session_id':'s','turn_id':'t1'}, _connection_key='private-key')
    log=ToolLog()
    payload={'session_id':'s','items':items()}
    log.observe(model,payload)
    text='\n'.join(records(caplog))
    assert 'count_words' in text and 'words=3' in text
    assert 'command=python report.py' in text and 'exit_code=0' in text and 'duration_ms=12' in text
    assert 'MCP docs/read' in text and 'read complete' in text and 'action=search' in text
    assert 'BASE64_PRIVATE' not in text and 'NEVER' not in text and 'private query' not in text
    count=len(records(caplog))
    log.observe(model,payload)
    log.observe(model,{'session_id':'wrong','items':items()})
    log.observe(model,{'session_id':'s','items':[dict(i,turn_id='old') for i in items()]})
    assert len(records(caplog))==count


@pytest.mark.parametrize('status', ['failed','incomplete'])
def test_failure_output_redaction_and_limits(caplog,status,monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv('SYNTHETIC_MCP_TOKEN','opaque-mcp-value')
    model=SimpleNamespace(_state={'session_id':'s','turn_id':'t1'},_connection_key='private-key',
                          _tool_log_key='resolved-api-value',_tool_settings={'mcp_servers':[{'authorization_env':'SYNTHETIC_MCP_TOKEN'}]})
    output='\x1b[31m\rINJECT\n[INFO] forged Bearer bearer-secret password=hunter2\nhttps://u:p@example.com/result?arbitrary=signature#secret\nprivate-key sk-secret opaque-mcp-value resolved-api-value '+ 'x'*5000
    item=dict(id='cmd',type='command_execution',command='password=cmd-secret',output=output,exit_code=1,status=status,turn_id='t1',stderr='UNUSED_SECRET')
    ToolLog().observe(model,{'items':[item]})
    text=records(caplog)[0]
    for secret in ('bearer-secret','hunter2','signature','private-key','sk-secret','cmd-secret','UNUSED_SECRET','u:p','opaque-mcp-value','resolved-api-value','\x1b','\r'):
        assert secret not in text
    assert 'exit_code=1' in text and '已截断' in text and '\n    [INFO]' in text


def test_real_accept_download_and_reconnect_share_logging(env,monkeypatch,tmp_path,caplog):
    caplog.set_level(logging.INFO)
    model=select(env)
    import tempfile
    from pathlib import Path
    folder=Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-',dir=tmp_path))
    file=folder/'report.pdf';file.write_bytes(b'synthetic')
    artifact=dict(id='f',session_id='s',turn_id='t1',name='report.pdf',path=str(file),status='ready',size=9)
    final_items=items()+[message('u','question',role='user'),message('a','answer')]
    def worker(command):
        if command['action'] in ('run','recover'):
            yield dict(type='result',session_id='s',turn_id='t1',outcome='completed',sync_complete=True,items=final_items)
        elif command['action']=='download':
            yield dict(type='progress',session_id='s',artifacts=[dict(artifact,turn_id='old',id='old')])
            yield dict(type='result',session_id='s',artifacts=[artifact])
        else:
            raise AssertionError(command)
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    send(env,model,'question')
    first=records(caplog)
    assert any('代码/文件执行' in line for line in first)
    assert sum('生成文件：report.pdf [ready]' in line for line in first)==1
    assert not any('old' in line or str(folder) in line for line in first)
    list(model.reconnect())
    list(model.retry_artifact('f'))
    assert records(caplog)==first


def test_file_failure_scope_and_safe_error(caplog):
    caplog.set_level(logging.INFO)
    model=SimpleNamespace(_state={'session_id':'s','turn_id':'t1'},_connection_key='private-key')
    log=ToolLog()
    record=dict(id='f',session_id='s',turn_id='t1',name='/private/report.pdf',size=12,status='failed',
                path='/Users/private/key',remote_path='/sandbox/private/report.pdf',error='read /Users/private/key password=hidden')
    log.observe(model,{},[record,dict(record,id='old',turn_id='old'),dict(record,id='other',session_id='other')])
    text=records(caplog)
    assert len(text)==1 and 'report.pdf [failed]' in text[0]
    assert '/Users' not in text[0] and '/sandbox' not in text[0] and 'hidden' not in text[0]
    log.observe(model,{},[record])
    assert records(caplog)==text


def test_input_log_is_safe_and_not_protocol_dump(env,monkeypatch,caplog):
    caplog.set_level(logging.INFO)
    model=select(env)
    def worker(command):
        if command['action']=='run':
            yield dict(type='result',session_id='s',turn_id='t1',outcome='completed',text='answer')
        else:
            yield dict(type='result',artifacts=[])
    monkeypatch.setattr(env.agents,'worker_messages',worker)
    send(env,model,'request password=hidden')
    inputs=[r.getMessage() for r in caplog.records if '的输入为：' in r.getMessage()]
    assert len(inputs)==1 and 'hidden' not in inputs[0] and '[REDACTED]' in inputs[0]


@pytest.mark.parametrize('value', [
    'password="abc,TAIL_SECRET"',
    '{"password":"abc,TAIL_SECRET"}',
    "password='abc;TAIL_SECRET'",
    '{"password":"abc\\\";TAIL_SECRET"}',
])
def test_quoted_credentials_are_redacted_whole(value):
    cleaned=safe_text(value)
    assert 'abc' not in cleaned and 'TAIL_SECRET' not in cleaned
    assert '[REDACTED]' in cleaned


def test_known_secret_redaction_runs_after_terminal_normalization():
    cleaned=safe_text('output opaque-\x1b[31mmcp-value',secrets=('opaque-mcp-value',))
    assert cleaned=='output [REDACTED]'


@pytest.mark.parametrize('value', [
    'Cookie: theme=dark; session=SESSION_SECRET; csrftoken=CSRF_SECRET',
    'Authorization: Basic BASIC_SECRET; suffix=TAIL_SECRET',
    'password=abc,TAIL_SECRET',
    'password=abc;TAIL_SECRET',
])
def test_unquoted_credentials_and_headers_hide_entire_line(value):
    cleaned=safe_text(value+'\nordinary next line')
    for secret in ('SESSION_SECRET','CSRF_SECRET','BASIC_SECRET','TAIL_SECRET','abc','theme=dark'):
        assert secret not in cleaned
    assert '[REDACTED]' in cleaned and 'ordinary next line' in cleaned
