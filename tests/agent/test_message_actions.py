"""Offline integration of real server message markup and browser action scripts.

The DOM harness exercises production JavaScript, not a browser layout engine.
No hosted Agent, real clipboard, network or native file download is used.
"""
import ast
from dataclasses import asdict
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

from modules.agent.ui import AgentPanel, ArtifactPanel
from modules.model_capabilities import AGENT_CAPABILITIES, ModelCapabilities


ROOT = Path(__file__).resolve().parents[2]
ORDINARY_RAW = '# 报告 **重要**\n\n- café / 中文 / 😀\n- [链接](https://example.test)\n`quoted code` & "text"\n末行\n'
RAW = ORDINARY_RAW + '    四个空格缩进\n字面实体 &amp; &#42; &lt;\n'


def _formatters():
    # Import these exact pure production functions without importing utils.py's
    # unrelated model/provider initializers. The server's escaping and newline
    # conversion are part of the contract, so do not replace them with a fixture.
    source = ast.parse((ROOT / 'modules/utils.py').read_text())
    names = {'clip_rawtext', 'escape_markdown', 'convert_bot_before_marked',
             'convert_user_before_marked'}
    functions = [node for node in source.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in functions} == names
    namespace = {'re': re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'modules/utils.py', 'exec'), namespace)
    return namespace['convert_user_before_marked'], namespace['convert_bot_before_marked']


class AgentFixture(SimpleNamespace):
    is_hosted_agent = True
    ui_capabilities = AGENT_CAPABILITIES


def _render(conversation, formatters, shortened=False):
    rows = [['first?', RAW], ['second?', RAW], ['files only?', None]]
    model = AgentFixture(
        _conversation_id=conversation,
        _display=rows[1:] if shortened else rows,
        _cloud_items=[
            dict(id='u1', role='user', content='first?', turn_id='t1'),
            dict(id='a1', role='assistant', content=RAW, turn_id='t1'),
            dict(id='u2', role='user', content='second?', turn_id='t2'),
            dict(id='a2', role='assistant', content=RAW, turn_id='t2'),
            dict(id='u3', role='user', content='files only?', turn_id='t3'),
        ],
        _artifacts=[
            dict(id='ready-second', name='same.txt', session_id='session', turn_id='t2',
                 status='ready', path='/tmp/private-second/same.txt', size=64),
            dict(id='ready-first', name='same.txt', session_id='session', turn_id='t1',
                 status='ready', path='/tmp/private-first/same.txt', size=32),
            dict(id='failed-first', name='same.txt', session_id='session', turn_id='t1',
                 status='failed', error='synthetic failure', size=32),
            dict(id='file-only', name='empty-answer.txt', session_id='session', turn_id='t3',
                 status='ready', path='/tmp/private-empty/empty-answer.txt', size=8),
        ],
        _state={'session_id': 'session', 'turn_id': 't3'},
        _answer_row=None,
    )
    values = ArtifactPanel.values(model)
    return {
        'conversation': conversation,
        'rows': AgentPanel(*formatters).render_chat(model, model._display),
        'cards': values[1]['value'],
        'nativeIds': json.loads(values[2]['label']),
    }


def test_real_chat_refresh_copy_markdown_and_file_actions():
    formatters = _formatters()
    payload = {
        'raw': RAW,
        'ordinaryRaw': ORDINARY_RAW,
        # Legacy escaping transforms indentation and named entities, but escapes
        # the # in numeric entities. Preserve that existing fallback contract.
        'legacyRaw': RAW.replace('    ', '\u00a0' * 4).replace('&amp;', '&').replace('&lt;', '<'),
        'agentCaps': asdict(AGENT_CAPABILITIES),
        'normalCaps': asdict(ModelCapabilities()),
        'initial': _render('conversation', formatters),
        'restored': _render('restored', formatters),
        'shortened': _render('restored-short', formatters, shortened=True),
        'ordinary': formatters[1](ORDINARY_RAW),
    }
    result = subprocess.run(
        [shutil.which('node') or 'node', 'tests/javascript/message-actions.test.cjs'],
        cwd=ROOT, input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'message action regressions passed' in result.stdout
