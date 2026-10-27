"""Explicit Agent tools and request-scoped browser approvals.

The registry contains executable application functions, never code supplied by
chat/history. Credentials are resolved only for requests and are not snapshots.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import hashlib
import ipaddress
import socket
import os
from pathlib import Path
import re
from threading import Event, RLock, Thread
from urllib.parse import urlsplit


class ToolConfigurationError(ValueError):
    pass


DEFAULT_SETTINGS = {
    'network': True, 'code_execution': True,
    'web_search': True, 'search_mode': 'live', 'search_domains': [],
    'computer_use': True, 'include_screenshots': False,
    'tool_search': False, 'programmatic_tool_calling': False,
    'functions': [], 'mcp_servers': [],
}
FUNCTIONS = {}
_running = {}
_lock = RLock()
CONTROL_ROOT = Path(__file__).resolve().parents[2] / 'agent_data' / 'task_control'


def _control_folder(session_id, turn_id):
    digest = hashlib.sha256((session_id + ':' + turn_id).encode()).hexdigest()
    folder = CONTROL_ROOT / digest
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def _write_control(path, value):
    from uuid import uuid4
    temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream: json.dump(value, stream)
    temporary.replace(path)



@dataclass
class RegisteredFunction:
    schema: dict
    execute: object
    cancel: object = None
    authorized: object = lambda: True


def register_function(name, description, parameters, execute, *, cancel=None, authorized=lambda: True):
    if not callable(execute) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', name):
        raise ToolConfigurationError('函数必须具有有效名称和可执行实现')
    FUNCTIONS[name] = RegisteredFunction({'type': 'function', 'name': name, 'description': description,
                                         'parameters': deepcopy(parameters)}, execute, cancel, authorized)


def _statistics(arguments, stop):
    text = arguments['text']
    return {'characters': len(text), 'lines': len(text.splitlines()), 'words': len(text.split())}


register_function('text_statistics', 'Count characters, lines and words in supplied text.',
                  {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}, _statistics)


def _origin(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ('https', 'http') and bool(parsed.hostname) and not parsed.username and not parsed.password and parsed.path in ('', '/') and not parsed.query and not parsed.fragment
    except (ValueError, TypeError):
        return False


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) - set(DEFAULT_SETTINGS):
        raise ToolConfigurationError('工具配置包含未知字段')
    result = dict(deepcopy(DEFAULT_SETTINGS), **deepcopy(settings))
    for key in ('network', 'code_execution', 'web_search', 'computer_use', 'include_screenshots', 'tool_search', 'programmatic_tool_calling'):
        if type(result[key]) is not bool:
            raise ToolConfigurationError(key + ' 必须为开或关')
    if result['search_mode'] not in ('live', 'cached', 'disabled'):
        raise ToolConfigurationError('网页搜索模式应为 live、cached 或 disabled')
    domains = result['search_domains']
    if not isinstance(domains, list) or any(not isinstance(d, str) or not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?', d) for d in domains):
        raise ToolConfigurationError('搜索范围请填写域名，不含协议、路径或通配符')
    if result['computer_use'] and not result['code_execution']:
        raise ToolConfigurationError('云端浏览器依赖云端执行环境；请同时开启代码与文件执行，或关闭浏览器')
    if result['programmatic_tool_calling'] and not result['code_execution']:
        raise ToolConfigurationError('程序化工具调用依赖云端执行环境')
    names = result['functions']
    if not isinstance(names, list) or len(names) != len(set(names)):
        raise ToolConfigurationError('请选择有效且不重复的函数')
    for name in names:
        entry = FUNCTIONS.get(name)
        if entry is None or not callable(entry.execute):
            raise ToolConfigurationError('函数没有已注册的可执行实现：' + str(name))
        if not entry.authorized():
            raise ToolConfigurationError('函数授权已失效：' + name)
    servers = result['mcp_servers']
    if not isinstance(servers, list):
        raise ToolConfigurationError('MCP 配置应为服务器列表')
    labels = set()
    for server in servers:
        if not isinstance(server, dict) or set(server) - {'server_label', 'server_url', 'allowed_tools', 'authorization_env', 'enabled', 'connection_origin'}:
            raise ToolConfigurationError('MCP 仅支持明确的 HTTP 服务器、环境变量凭据引用和工具范围')
        label = server.get('server_label', '')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', label) or label in labels:
            raise ToolConfigurationError('MCP 服务器名称无效或重复')
        labels.add(label)
        parsed = urlsplit(server.get('server_url', ''))
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ToolConfigurationError('MCP 地址无效；不能在地址中填写凭据')
        allowed = server.get('allowed_tools')
        if not isinstance(allowed, list) or not allowed or any(not isinstance(x, str) or not x or x == '*' for x in allowed):
            raise ToolConfigurationError('请逐项指定 MCP 开放的工具；不能省略范围或使用 *')
        if server.get('authorization_env') and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', server['authorization_env']):
            raise ToolConfigurationError('MCP 凭据应引用服务器环境变量名，不能填写真实凭据')
        if server.get('connection_origin', 'service') not in ('service', 'environment'):
            raise ToolConfigurationError('MCP 连接来源无效')
        if server.get('connection_origin') == 'environment' and not result['code_execution']:
            raise ToolConfigurationError('MCP environment 连接需要云端执行环境')
        if 'enabled' in server and type(server['enabled']) is not bool:
            raise ToolConfigurationError('MCP enabled 必须为开或关')
    return result


def tool_availability(settings, *, environ=None):
    settings = validate_settings(settings)
    environ = os.environ if environ is None else environ
    rows = []
    for key, label in [('code_execution', '代码与文件执行'), ('web_search', '网页搜索'), ('computer_use', '云端浏览器'), ('tool_search', '工具发现'), ('programmatic_tool_calling', '程序化工具调用')]:
        reason = ''
        status = '已启用' if settings[key] else '已关闭'
        if key == 'web_search' and settings['search_mode'] == 'disabled': status = '已关闭'
        if key == 'tool_search' and settings[key] and not settings['functions']:
            status, reason = '需要配置或授权', '配置并启用可发现的函数后生效'
        rows.append([label, status, reason])
    for name in settings['functions']:
        rows.append([name, '已启用', '已注册应用函数'])
    for server in settings['mcp_servers']:
        if not server.get('enabled', True): status, reason = '已关闭', ''
        elif server.get('authorization_env') and not environ.get(server['authorization_env']):
            status, reason = '需要配置或授权', '服务器凭据引用不可用'
        else: status, reason = '需要配置或授权', '新会话创建前验证连接与指定工具范围'
        rows.append(['MCP ' + server['server_label'], status, reason])
    return rows


def _mcp_binding(server, environ, owner=None):
    """服务器注册表约束凭据、用户、工具及私网例外；客户端不能扩权。"""
    try:
        registry = json.loads(environ.get('CHUANHU_AGENT_MCP_AUTHORIZATION', '{}'))
        if not isinstance(registry, dict): raise ValueError()
    except (ValueError, TypeError):
        raise ToolConfigurationError('MCP 服务器授权配置无效') from None
    binding = registry.get(server['server_label'])
    if binding is None:
        if server.get('authorization_env'):
            raise ToolConfigurationError('MCP 凭据未绑定到可信服务器：' + server['server_label'])
        return None
    if (not isinstance(binding, dict) or binding.get('server_url') != server['server_url']
            or binding.get('authorization_env') != server.get('authorization_env')):
        raise ToolConfigurationError('MCP 配置与服务器授权不一致：' + server['server_label'])
    owners = binding.get('owners', [])
    if binding.get('shared') is not True and (not isinstance(owner, str) or not owner
            or not isinstance(owners, list) or owner not in owners):
        raise ToolConfigurationError('当前用户没有此 MCP 连接的权限')
    allowed = binding.get('allowed_tools')
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(name, str) or not name or name == '*' for name in allowed)
            or not set(server['allowed_tools']) <= set(allowed)):
        raise ToolConfigurationError('MCP 工具超出服务器授权范围')
    return binding


def mcp_authorization(server, environ, owner=None):
    """只在完成服务器授权检查后读取相应凭据，不返回到聊天配置。"""
    binding = _mcp_binding(server, environ, owner)
    ref = server.get('authorization_env')
    if not ref: return None
    if urlsplit(server['server_url']).scheme != 'https' and not binding.get('allow_private') is True:
        raise ToolConfigurationError('MCP 凭据需要 HTTPS，私网 HTTP 必须由管理员明确授权')
    value = environ.get(ref)
    if not value: raise ToolConfigurationError('MCP 认证不可用：' + server['server_label'])
    return value


# 转换/隧道地址可能把 IPv6 公网表象映射到 IPv4 私网；不依赖各 Python 版本的分类表。
_MCP_TRANSITION_NETWORKS = tuple(ipaddress.ip_network(prefix) for prefix in (
    '64:ff9b::/96', '64:ff9b:1::/48', '2002::/16', '2001::/32',
    '::/96', '::ffff:0:0:0/96',
))


def _mcp_probe_destination(server, binding):
    """解析一次并固定 IP；保留原 Host/SNI，禁止再次 DNS 解析及代理绕过。"""
    import httpx
    parsed = urlsplit(server['server_url'])
    try:
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        addresses = list(dict.fromkeys(record[4][0] for record in
            socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)))
        if not addresses: raise ValueError()
        private_allowed = bool(binding and binding.get('allow_private') is True)
        for value in addresses:
            address = ipaddress.ip_address(value)
            mapped = getattr(address, 'ipv4_mapped', None)
            checked = mapped or address
            transition = address.version == 6 and any(address in prefix for prefix in _MCP_TRANSITION_NETWORKS)
            if not private_allowed and (transition or not checked.is_global or checked.is_multicast or checked.is_reserved):
                raise ToolConfigurationError('MCP 私网地址需要管理员明确授权')
        original = httpx.URL(server['server_url'])
        pinned = original.copy_with(host=addresses[0])
        return str(pinned), original.netloc.decode('ascii'), parsed.hostname
    except ToolConfigurationError:
        raise
    except (OSError, ValueError, TypeError):
        raise ToolConfigurationError('MCP 服务器地址无法安全解析') from None


def probe_mcp(server, *, http_client=None, environ=None, owner=None):
    """Read-only MCP initialize/list probe before exposing a configured server."""
    import httpx
    environ = os.environ if environ is None else environ
    binding = _mcp_binding(server, environ, owner)
    value = mcp_authorization(server, environ, owner)
    destination, host, tls_hostname = _mcp_probe_destination(server, binding)
    headers = {'Accept': 'application/json, text/event-stream', 'Host': host}
    if value: headers['Authorization'] = value
    own = http_client is None
    client = http_client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
    try:
        def call(method, params=None, identifier=None):
            payload = {'jsonrpc': '2.0', 'method': method}
            if identifier is not None: payload['id'] = identifier
            if params is not None: payload['params'] = params
            response = client.post(destination, json=payload, headers=headers, follow_redirects=False,
                                   extensions={'sni_hostname': tls_hostname})
            response.raise_for_status()
            sid = response.headers.get('mcp-session-id')
            if sid: headers['Mcp-Session-Id'] = sid
            if not response.content: return {}
            if 'text/event-stream' in response.headers.get('content-type', ''):
                data = [line[5:].strip() for line in response.text.splitlines() if line.startswith('data:')]
                messages = [json.loads(line) for line in data]
                body = next((message for message in messages if message.get('id') == identifier), {})
            else: body = response.json()
            if body.get('error'): raise ToolConfigurationError('MCP 返回连接或工具范围错误：' + server['server_label'])
            return body.get('result', {})
        result = call('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'ChuanhuChat', 'version': '1'}}, 1)
        if not result.get('protocolVersion'): raise ToolConfigurationError('MCP 初始化未成功：' + server['server_label'])
        headers['MCP-Protocol-Version'] = result['protocolVersion']
        call('notifications/initialized')
        names, cursor, cursors = set(), None, set()
        while True:
            result = call('tools/list', {'cursor': cursor} if cursor else {}, 2)
            names.update(tool['name'] for tool in result.get('tools', []) if isinstance(tool.get('name'), str))
            cursor = result.get('nextCursor')
            if not cursor: break
            if cursor in cursors: raise ToolConfigurationError('MCP 工具分页重复，未确认完整范围')
            cursors.add(cursor)
        if not set(server['allowed_tools']) <= names:
            raise ToolConfigurationError('MCP 指定的工具不存在或无访问权限：' + server['server_label'])
        return True
    except ToolConfigurationError: raise
    except Exception:
        raise ToolConfigurationError('MCP 连接或认证失败：' + server['server_label']) from None
    finally:
        if own: client.close()


def build_tool_config(settings, *, verify_connections=True, environ=None, owner=None):
    settings = validate_settings(settings)
    environ = os.environ if environ is None else environ
    tools = []
    if settings['web_search'] and settings['search_mode'] != 'disabled':
        tools.append({'type': 'web_search', 'mode': settings['search_mode'], 'allowed_domains': settings['search_domains']})
    if settings['computer_use']:
        tools.append({'type': 'computer_use', 'include_screenshots': settings['include_screenshots']})
    for name in settings['functions']:
        tool = deepcopy(FUNCTIONS[name].schema)
        if settings['tool_search']: tool['defer_loading'] = True
        tools.append(tool)
    if settings['tool_search'] and settings['functions']: tools.append({'type': 'tool_search'})
    if settings['programmatic_tool_calling']: tools.append({'type': 'programmatic_tool_calling', 'enabled': True})
    for server in settings['mcp_servers']:
        if not server.get('enabled', True): continue
        _mcp_binding(server, environ, owner)
        if verify_connections: probe_mcp(server, environ=environ, owner=owner)
        transport = {'type': 'http', 'server_url': server['server_url']}
        if server.get('authorization_env'):
            value = mcp_authorization(server, environ, owner)
            transport['authorization'] = value
        tools.append({'type': 'mcp', 'server_label': server['server_label'], 'transport': transport,
                      'allowed_tools': list(server['allowed_tools']), 'connection_origin': server.get('connection_origin', 'service')})
    environment = {'type': 'none'}
    if settings['code_execution']:
        environment = {'type': 'openai_hosted', 'network': {'access': 'enabled' if settings['network'] else 'disabled'}}
        if settings['computer_use']: environment['desktop'] = {'enabled': True}
    return {'tools': tools, 'environment': environment, 'snapshot': settings}


def pending_action_cards(session, turn_id):
    cards = []
    for action in session.get('required_actions') or []:
        if action.get('turn_id') != turn_id or action.get('type') != 'computer_use_approval_request': continue
        request = deepcopy(action.get('request') or {})
        # Schema contains form descriptions, never credential values.
        if request.get('type') not in ('browser_origin_access', 'browser_authentication'): continue
        cards.append({'request_id': action['request_id'], 'turn_id': turn_id, 'request': request})
    return cards


def submit_browser_response(client, session_id, turn_id, request_id, response):
    session = client.beta.agents.sessions.retrieve(session_id)
    session = session if isinstance(session, dict) else session.model_dump()
    cards = pending_action_cards(session, turn_id)
    card = next((item for item in cards if item['request_id'] == request_id), None)
    if card is None or session.get('status') in ('idle', 'failed'):
        raise ToolConfigurationError('该请求已处理、已停止或不属于当前任务，请重新连接查看状态')
    request = card['request']
    if not isinstance(response, dict) or response.get('type') != request['type']:
        raise ToolConfigurationError('授权类型与当前请求不一致')
    if request['type'] == 'browser_origin_access':
        if not _origin(request.get('origin')) or set(response) != {'type', 'decision'} or response.get('decision') not in ('approve', 'deny', 'cancel'):
            raise ToolConfigurationError('请只批准、拒绝或取消当前网站请求')
    else:
        if response.get('action') == 'cancel':
            if set(response) != {'type', 'action'}: raise ToolConfigurationError('取消登录不能附带凭据')
        elif response.get('action') == 'submit':
            if not _origin(request.get('credential_origin')): raise ToolConfigurationError('登录网站不明确，不能提交凭据')
            if set(response) - {'type', 'action', 'fields', 'selected_option'}: raise ToolConfigurationError('登录表单包含未知字段')
            fields = {field['id']: field for field in request.get('fields') or []}
            options = request.get('options') or []
            if options:
                option = next((item for item in options if item['id'] == response.get('selected_option')), None)
                if option is None: raise ToolConfigurationError('请选择当前请求提供的登录方式')
                if not set(option.get('field_ids', [])) <= set(fields): raise ToolConfigurationError('登录表单字段不完整')
                fields = {key: fields[key] for key in option.get('field_ids', [])}
            elif 'selected_option' in response: raise ToolConfigurationError('当前登录请求没有方式选项')
            values = response.get('fields')
            if not isinstance(values, list): raise ToolConfigurationError('登录字段无效')
            names = [field.get('field_id') for field in values if isinstance(field, dict)]
            if len(names) != len(values) or len(names) != len(set(names)) or not set(names) <= set(fields): raise ToolConfigurationError('登录字段不属于当前请求')
            if fields and not values: raise ToolConfigurationError('请填写登录字段或取消')
            entered = {}
            for field in values:
                if set(field) != {'field_id', 'value'} or not isinstance(field['value'], str): raise ToolConfigurationError('登录字段格式无效')
                entered[field['field_id']] = field['value']
            if any(field.get('required') and not entered.get(key) for key, field in fields.items()): raise ToolConfigurationError('请填写必填登录字段')
        else: raise ToolConfigurationError('登录操作无效')
    client.beta.agents.sessions.events.create(session_id, events=[{'type': 'agent.session.input.computer_use_approval_request_result', 'request_id': request_id, 'response': response}])
    return {'accepted': True, 'message': '已提交，等待网站与任务确认；这不代表已经登录成功'}


def handle_function_actions(client, state, session, settings, handled, *, on_activity=None):
    import jsonschema
    settings = validate_settings(settings)
    for action in session.get('required_actions') or []:
        if action.get('type') != 'function_call' or action.get('turn_id') != state.turn_id: continue
        call_id, name = action.get('call_id'), action.get('name')
        if call_id in handled: continue
        if not isinstance(call_id, str) or not call_id:
            raise ToolConfigurationError('函数调用标识无效')
        entry = FUNCTIONS.get(name)
        if name not in settings['functions'] or entry is None or not entry.authorized():
            raise ToolConfigurationError('函数未启用、不可执行或授权已失效：' + str(name))
        arguments = action.get('arguments')
        try:
            if isinstance(arguments, str): arguments = json.loads(arguments)
        except ValueError:
            arguments = None
        digest = hashlib.sha256(json.dumps({'name': name, 'arguments': arguments}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        folder = _control_folder(state.session_id, state.turn_id)
        identifier = hashlib.sha256(call_id.encode()).hexdigest()
        control, claim, saved_result = folder / (identifier + '.json'), folder / (identifier + '.claim'), folder / (identifier + '.result')
        if (folder / 'cancel').exists():
            raise ToolConfigurationError('当前轮已请求停止，不再启动或恢复应用函数')
        try:
            descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                previous = json.loads(claim.read_text())
                if previous.get('digest') != digest:
                    raise ToolConfigurationError('同一函数调用标识的参数已变化，未重复执行')
                cached = json.loads(saved_result.read_text())
            except (OSError, ValueError):
                raise ToolConfigurationError('该函数已经启动，执行结果尚待确认；不会重新执行可能产生副作用的操作') from None
            if cached.get('digest') != digest:
                raise ToolConfigurationError('函数结果与当前请求不一致，未重复执行')
            result = cached['result']
            # A recorded accepted submission must not be replayed from an older
            # required_action snapshot. The next session read decides progress.
            if cached.get('submission') == 'accepted':
                if on_activity:on_activity(action,'failed' if result.get('success') is False else 'completed')
                handled.add(call_id)
                continue
        else:
            with os.fdopen(descriptor, 'w') as claim_file:
                json.dump({'call_id': call_id, 'digest': digest}, claim_file)
                claim_file.flush()
                os.fsync(claim_file.fileno())
            try:
                jsonschema.validate(arguments, entry.schema['parameters'])
            except (jsonschema.ValidationError, jsonschema.SchemaError):
                result = {'success': False, 'error': '函数参数不符合已注册的输入格式'}
                _write_control(control, {'call_id': call_id, 'status': 'completed'})
            else:
                stop, finished = Event(), Event()
                _write_control(control, {'call_id': call_id, 'status': 'running'})
                def watch_cancel():
                    while not finished.wait(0.05):
                        if (folder / 'cancel').exists():
                            stop.set()
                            _write_control(control, {'call_id': call_id, 'status': 'cancel_requested'})
                            if entry.cancel:
                                try: entry.cancel()
                                except Exception: pass
                            return
                monitor = Thread(target=watch_cancel, daemon=True)
                monitor.start()
                with _lock: _running[(state.session_id, state.turn_id, call_id)] = (stop, entry.cancel)
                try:
                    if on_activity:on_activity(action,'running')
                    output = entry.execute(arguments, stop)
                    if stop.is_set(): result = {'success': False, 'error': '当前任务已请求停止'}
                    else: result = {'success': True, 'output': json.dumps(output, ensure_ascii=False)}
                except Exception: result = {'success': False, 'error': '应用函数执行失败；未自动重试'}
                finally:
                    finished.set()
                    monitor.join()
                    _write_control(control, {'call_id': call_id, 'status': 'stopped' if stop.is_set() else 'completed'})
                    with _lock: _running.pop((state.session_id, state.turn_id, call_id), None)
            # Persist before the first result transmission. A lost acknowledgement
            # can reuse this result, never invoke the function a second time.
            _write_control(saved_result, {'digest': digest, 'result': result, 'submission': 'pending'})
        if on_activity:on_activity(action,'failed' if result.get('success') is False else 'completed')
        handled.add(call_id)
        try:
            client.beta.agents.sessions.events.create(state.session_id, events=[{'type': 'agent.session.input.tool_result', 'turn_id': state.turn_id, 'call_id': call_id, **result}])
        except Exception:
            _write_control(saved_result, {'digest': digest, 'result': result, 'submission': 'uncertain'})
            raise
        _write_control(saved_result, {'digest': digest, 'result': result, 'submission': 'accepted'})


def cancel_application_tasks(session_id, turn_id):
    """Signal functions in the original worker, not just this cancel process."""
    if not session_id or not turn_id: return []
    folder = _control_folder(session_id, turn_id)
    _write_control(folder / 'cancel', {'cancel_requested': True})
    results = []
    for path in folder.glob('*.json'):
        try:
            value = json.loads(path.read_text())
            status = value.get('status')
            results.append({'call_id': value['call_id'], 'status': status,
                            'confirmed': status in ('stopped', 'completed')})
        except (OSError, ValueError, KeyError):
            results.append({'status': 'unknown', 'confirmed': False})
    return results
