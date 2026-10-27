"""Readable host-side tool summaries; never write to the worker protocol."""
import hashlib
import logging
import os
import re
from threading import RLock
from urllib.parse import urlsplit, urlunsplit


TERMINAL = {'completed', 'failed', 'incomplete'}


def known_secrets(model):
    names = ['OPENAI_API_KEY', 'CHUANHU_AGENT_API_KEY']
    names.extend(server.get('authorization_env') for server in getattr(model, '_tool_settings', {}).get('mcp_servers', [])
                 if isinstance(server, dict) and server.get('authorization_env'))
    return (getattr(model, '_connection_key', None), getattr(model, '_tool_log_key', None),
            *(os.environ.get(name) for name in names))


def safe_text(value, limit=4000, secrets=()):
    if not isinstance(value, str):
        return ''
    text = value
    text = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)', '', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'[\x00-\x09\x0b-\x1f\x7f]', '', text)
    for secret in secrets:
        if isinstance(secret, str) and secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\bBearer\s+[^\s,;"\']+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    credential = r'(?i)(\b(?:password|passwd|api[_-]?key|token|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization|cookie|secret)\b["\']?\s*[:=]\s*)'
    # Consume quoted values before delimiter-based unquoted values. JSON escapes
    # and embedded commas/semicolons belong to the credential, not a new field.
    text = re.sub(credential + r'"(?:\\.|[^"\\])*"', r'\1[REDACTED]', text)
    text = re.sub(credential + r"'(?:\\.|[^'\\])*'", r'\1[REDACTED]', text)
    # Unquoted credentials and header values may legitimately contain comma or
    # semicolon. Conservatively hide the rest of the line, including suffixes.
    text = re.sub(credential + r'[^\n]+', r'\1[REDACTED]', text)
    def clean_url(match):
        try:
            url = urlsplit(match.group())
            host = url.hostname or ''
            return urlunsplit((url.scheme, host, url.path, '', ''))
        except ValueError:
            return '[URL REDACTED]'
    text = re.sub(r'https?://[^\s<>"\']+', clean_url, text)
    # Indent continuation lines so tool output cannot impersonate a log header.
    text = text.replace('\n', '\n    ')
    return text if len(text) <= limit else text[:limit] + '… [已截断]'


def output_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(output_text(part) for part in value if isinstance(part, (str, dict)))
    if isinstance(value, dict):
        if value.get('type') in ('input_image', 'image', 'computer_screenshot'):
            return '[图像内容省略]'
        # Arbitrary MCP objects are not serialized: only familiar text fields.
        return '\n'.join(output_text(value[key]) for key in ('text', 'message', 'content', 'output') if key in value)
    return ''


class ToolLog:
    def __init__(self):
        self.lock = RLock()
        self.names = {}
        self.seen = set()

    def emit(self, key, text):
        digest = hashlib.sha256(text.encode()).hexdigest()
        marker = (*key, digest)
        if marker not in self.seen:
            self.seen.add(marker)
            logging.info('%s', text)

    def observe(self, model, message, artifacts=()):
        with self.lock:
            self._observe(model, message, artifacts)

    def _observe(self, model, message, artifacts=()):
        session, turn = model._state.get('session_id'), model._state.get('turn_id')
        if not session or not turn or message.get('session_id', session) != session:
            return
        secrets = known_secrets(model)
        clean = lambda value, limit=4000: safe_text(value, limit, secrets)
        items = [item for item in message.get('items', []) if isinstance(item, dict) and item.get('turn_id') == turn]
        for item in items:
            if item.get('type') == 'function_call' and item.get('call_id'):
                self.names[(session, turn, item['call_id'])] = clean(item.get('name', ''), 100)
        for item in items:
            kind, status = item.get('type'), item.get('status')
            identifier = item.get('id') or item.get('call_id')
            if not identifier or status not in TERMINAL:
                continue
            details = []
            if kind == 'command_execution':
                name = '代码/文件执行'
                details = [('command', clean(item.get('command'), 500)), ('exit_code', item.get('exit_code') if type(item.get('exit_code')) is int else ''),
                           ('duration_ms', item.get('duration_ms') if type(item.get('duration_ms')) in (int, float) else ''), ('output', clean(output_text(item.get('output'))))]
            elif kind == 'function_call_output':
                name = self.names.get((session, turn, item.get('call_id')), 'function')
                details = [('output', clean(output_text(item.get('output')))), ('error', clean(output_text(item.get('error'))))]
            elif kind == 'mcp_call':
                name = 'MCP ' + clean(item.get('server_label', ''), 100) + '/' + clean(item.get('name', ''), 100)
                details = [('output', clean(output_text(item.get('output')))), ('error', clean(output_text(item.get('error'))))]
            elif kind == 'web_search_call':
                name = '网页搜索'
                action = item.get('action')
                details = [('action', clean(action if isinstance(action, str) else (action or {}).get('type', ''), 100))]
            else:
                continue
            result = '; '.join(f'{key}={value}' for key, value in details if value != '' and value is not None)
            self.emit((session, turn, 'tool', kind, identifier), f'工具结果：{name} [{status}]' + (' ' + result if result else ''))
        for record in artifacts:
            if (record.get('session_id') != session or record.get('turn_id') != turn
                    or record.get('status') not in ('ready', 'failed') or not record.get('id')):
                continue
            name = clean(str(record.get('name', '')).replace('\\', '/').rsplit('/', 1)[-1], 200)
            size = record.get('size') if type(record.get('size')) is int else '未知'
            error = clean(output_text(record.get('error')), 500)
            error = re.sub(r'(?:[A-Za-z]:[\\/]|/)[^\s,;]+', '[路径省略]', error)
            self.emit((session, turn, 'file', record['id']), f'生成文件：{name} [{record["status"]}] size={size}' + (' error=' + error if error else ''))
