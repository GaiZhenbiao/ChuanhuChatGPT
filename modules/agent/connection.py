"""One OpenAI SDK and explicit per-request connection settings for all Agent work.

The host resolves its existing user/configuration scope, then passes this small
snapshot to the worker over stdin. It must never be stored with chat history.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import urlsplit

OFFICIAL_BASE = 'https://api.openai.com/v1'
KEY_NAME = 'CHUANHU_AGENT_API_KEY'
PROXY_ENV = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
             'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
             'SSL_CERT_FILE', 'SSL_CERT_DIR')


class AgentConnectionError(ValueError):
    """A safe configuration error, containing no credentials or raw HTTP body."""


def read_optional_key(path=None, *, environ=None):
    """Existing dedicated keys remain optional overrides of the ordinary key."""
    environ = os.environ if environ is None else environ
    value = environ.get(KEY_NAME, '').strip()
    if value:
        return value
    path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / '.env.agents'
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise AgentConnectionError('Agent 专用密钥文件不能是符号链接，请检查配置。')
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        raise AgentConnectionError('无法读取 Agent 专用密钥文件，请检查配置。') from None
    matches = re.findall(r'^\s*CHUANHU_AGENT_API_KEY\s*=\s*(.*?)\s*$', text, re.M)
    if not matches:
        return None
    if len(matches) != 1:
        raise AgentConnectionError('Agent 专用密钥配置重复，请仅保留一项。')
    value = matches[0].strip().strip('\"\'')
    if not value:
        return None
    if any(character.isspace() for character in value):
        raise AgentConnectionError('Agent 专用密钥格式无效，请检查配置。')
    return value


def resolve_connection(api_key=None, api_base=None, organization=None, project=None,
                       dedicated_key=None, *, environ=None, credential_path=None):
    """Resolve an explicit snapshot without changing the process environment.

    Explicit scoped values win over environment values. The project's
    OPENAI_API_BASE wins over the SDK's OPENAI_BASE_URL when both are present.
    An optional Agent key overrides only the key, never the configured endpoint.
    Empty organization/project explicitly disables inherited SDK scope.
    """
    environ = os.environ if environ is None else environ
    override = dedicated_key or read_optional_key(credential_path, environ=environ)
    key = override or (api_key if api_key is not None else environ.get('OPENAI_API_KEY', ''))
    base = api_base if api_base is not None else (environ.get('OPENAI_API_BASE') or environ.get('OPENAI_BASE_URL') or OFFICIAL_BASE)
    if not isinstance(key, str) or not key.strip():
        raise AgentConnectionError('未配置 OpenAI API key，请填写原有 OpenAI 密钥；Agent 专用密钥仅作可选覆盖。')
    if not isinstance(base, str):
        raise AgentConnectionError('OpenAI API base 格式无效，请检查原有连接配置。')
    base = base.strip().rstrip('/')
    try:
        parsed = urlsplit(base)
    except ValueError:
        raise AgentConnectionError('OpenAI API base 格式无效，请检查原有连接配置。') from None
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise AgentConnectionError('OpenAI API base 必须是有效的 HTTP(S) 地址，不能包含凭据、查询参数或片段。')
    return {
        'api_key': key.strip(), 'base_url': base,
        'organization': organization if organization is not None else environ.get('OPENAI_ORG_ID', ''),
        'project': project if project is not None else environ.get('OPENAI_PROJECT_ID', ''),
        'proxy_env': {name: environ[name] for name in PROXY_ENV if name in environ},
    }


def worker_environment(connection, environ=None):
    """Apply captured proxy/TLS settings only to the child process.

    Keys and API scope are transmitted over stdin rather than inherited process
    settings or command arguments. Keep normal environment proxy semantics.
    """
    environment = dict(os.environ if environ is None else environ)
    for name in ('OPENAI_API_KEY', KEY_NAME, 'OPENAI_BASE_URL', 'OPENAI_API_BASE',
                 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID', 'OPENAI_LOG', *PROXY_ENV):
        environment.pop(name, None)
    proxy_env = connection.get('proxy_env', {})
    if not isinstance(proxy_env, dict) or any(name not in PROXY_ENV or not isinstance(value, str) for name, value in proxy_env.items()):
        raise AgentConnectionError('网络代理配置无效，请检查原有代理设置。')
    environment.update(proxy_env)
    return environment


def create_client(connection, *, http_client=None):
    """Build the shared SDK client. Reads retry; mutations never blindly replay.

    http_client is for offline tests. The production worker gets its proxy/TLS
    environment from worker_environment and uses the SDK's normal HTTP handling.
    No task lifetime is imposed: only individual connection/read waits time out.
    """
    try:
        import httpx2
        from openai import OpenAI, __version__ as sdk_version
    except ImportError:
        raise AgentConnectionError('请在主项目 Python 环境中安装更新后的 requirements.txt。') from None
    if tuple(int(part) for part in sdk_version.split('.')[:3]) < (3, 22, 0):
        raise AgentConnectionError('当前 OpenAI SDK 不支持完整 Agent 能力，请在主项目环境安装 openai 3.22.0 或更新版本。')
    if isinstance(connection, str):
        connection = resolve_connection(api_key=connection, dedicated_key=connection)
    if not isinstance(connection, dict):
        raise AgentConnectionError('缺少 OpenAI 连接配置，请检查原有设置。')
    if not isinstance(connection.get('api_key'), str) or not connection['api_key'].strip():
        raise AgentConnectionError('缺少 OpenAI API key，请检查原有设置。')
    # Validate the snapshot without consulting a different process key/scope.
    checked = resolve_connection(connection.get('api_key', ''), connection.get('base_url', ''),
                                 connection.get('organization', ''), connection.get('project', ''),
                                 dedicated_key=connection.get('api_key', ''), environ={})

    class ReadRetryOpenAI(OpenAI):
        def request(self, cast_to, options, *, stream=False, stream_cls=None):
            options = options.model_copy()
            options.max_retries = getattr(self, '_agent_read_retries', 2) if options.method.upper() in ('GET', 'HEAD') else 0
            return super().request(cast_to, options, stream=stream, stream_cls=stream_cls)

    client = ReadRetryOpenAI(api_key=checked['api_key'], base_url=checked['base_url'],
                            organization=checked['organization'] or '', project=checked['project'] or '',
                            max_retries=0, timeout=httpx2.Timeout(60, connect=15),
                            **({'http_client': http_client} if http_client is not None else {}))
    if not hasattr(getattr(client, 'beta', None), 'agents') or not hasattr(client.beta.agents.sessions, 'update'):
        client.close()
        raise AgentConnectionError('当前 OpenAI SDK 不支持所需 Agent 能力，请升级主项目依赖。')
    return client
