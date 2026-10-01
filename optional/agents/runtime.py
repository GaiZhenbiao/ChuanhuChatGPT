"""Optional Agents API adapter. Imports no SDK until explicitly requested.

Run in a dedicated environment, never the core Gradio/OpenAI 1.x environment.
No legacy plugin, tool, key, model selection or endpoint is inherited.
"""
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import time
import json
import tempfile
from itertools import islice

OFFICIAL_BASE = 'https://api.openai.com/v1'
KEY_NAME = 'CHUANHU_AGENT_API_KEY'


class AgentError(RuntimeError):
    def __init__(self, message, state=None):
        super().__init__(message)
        self.state = state


def read_dedicated_key(path=None):
    value = os.environ.get(KEY_NAME, '').strip()
    if value:
        return value
    path = Path(path) if path else Path(__file__).resolve().parents[2] / '.env.agents'
    if path.is_symlink():
        raise AgentError('Dedicated credential file must not be a symlink.')
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        raise AgentError('Dedicated Agents credential file is missing.') from None
    matches = re.findall(r'^\s*CHUANHU_AGENT_API_KEY\s*=\s*(.*?)\s*$', text, re.M)
    if len(matches) != 1:
        raise AgentError('Dedicated credential file must contain one CHUANHU_AGENT_API_KEY assignment.')
    value = matches[0].strip().strip('\"\'')
    if not value or any(c.isspace() for c in value):
        raise AgentError('Dedicated Agents credential is empty or malformed.')
    return value


def create_client(key):
    try:
        from openai import OpenAI
        import httpx2
    except ImportError:
        raise AgentError('Install optional/agents/requirements.txt in a separate Python 3.10+ environment.') from None
    # Disallow redirects and inherited endpoints/proxies. No response/exception
    # body is logged, since it can contain request data or sensitive material.
    transport = httpx2.Client(trust_env=False, follow_redirects=False, timeout=45)
    client = OpenAI(api_key=key, base_url=OFFICIAL_BASE, organization='', project='',
                    max_retries=0, timeout=45, http_client=transport)
    if not hasattr(getattr(client, 'beta', None), 'agents'):
        client.close()
        raise AgentError('This SDK lacks beta.agents; use the isolated Agents runtime.')
    return client


def as_dict(value):
    return value if isinstance(value, dict) else value.model_dump()


@dataclass
class TurnState:
    session_id: str | None = None
    turn_id: str | None = None
    outcome: str = 'incomplete'
    parts: dict = field(default_factory=dict)
    seen: set = field(default_factory=set)
    progress: str = ''
    ignored_turn_ids: set = field(default_factory=set)

    @property
    def text(self):
        return '\n'.join(value for _, value in sorted(self.parts.items(), key=lambda pair: (pair[0][1], pair[0][2], pair[0][0])))

    def accept(self, event):
        event = as_dict(event)
        kind = event.get('type', '')
        self.progress = kind
        session_id = event.get('session_id') or (event.get('session') or {}).get('id')
        if session_id:
            if self.session_id and session_id != self.session_id:
                return
            self.session_id = session_id
        event_id = event.get('event_id')
        if event_id:
            if event_id in self.seen:
                return
            self.seen.add(event_id)
        if kind in ('error', 'agent.session.failed', 'agent.session.environment.failed'):
            self.outcome = 'failed'
            raise AgentError('Agents session or environment failed; inspect saved session state.', self)
        turn = event.get('turn') or {}
        if turn.get('subagent_id') is not None:
            return
        turn_id = event.get('turn_id') or turn.get('id')
        if turn_id in self.ignored_turn_ids:
            return
        if kind in ('agent.session.turn.created', 'agent.session.turn.in_progress'):
            if self.turn_id is None:
                self.turn_id = turn_id
        if not turn_id or turn_id != self.turn_id:
            return
        if kind in ('agent.session.turn.output_text.delta', 'agent.session.turn.output_text.done'):
            item = event.get('item_id')
            output_index = event.get('output_index')
            content_index = event.get('content_index')
            if not isinstance(item, str) or type(output_index) is not int or type(content_index) is not int:
                return
            part = (item, output_index, content_index)
            if kind.endswith('.delta'):
                self.parts[part] = self.parts.get(part, '') + event.get('delta', '')
            else:
                self.parts[part] = event.get('text', '')
        if kind == 'agent.session.turn.completed':
            self.outcome = 'completed'
        elif kind in ('agent.session.turn.failed', 'agent.session.turn.cancelled'):
            self.outcome = kind.rsplit('.', 1)[-1]
            raise AgentError('Agents turn ' + self.outcome + '; no fallback request was made.', self)


def safe_request_error(error, state=None):
    status = getattr(error, 'status_code', None)
    if status == 401:
        message = 'OpenAI rejected the dedicated key (401); check the key and project.'
    elif status == 403:
        message = 'OpenAI denied access (403); check api.agents.read/write, api.responses.write and model access.'
    elif status is not None:
        message = f'Official Agents request failed (HTTP {status}); no retry or provider fallback was made.'
    else:
        message = 'Official Agents connection failed or timed out; inspect saved state before resubmitting.'
    return AgentError(message, state)


TEXT_TOOL = {'type': 'function', 'name': 'text_statistics',
             'description': 'Count characters, lines and whitespace-delimited words in supplied text. No file or network access.',
             'parameters': {'type': 'object', 'properties': {'text': {'type': 'string', 'maxLength': 20000}},
                            'required': ['text'], 'additionalProperties': False}}


def handle_function_actions(client, state, session, allowed, handled):
    actions = session.get('required_actions') or []
    for action in actions:
        if action.get('type') != 'function_call' or action.get('turn_id') != state.turn_id:
            raise AgentError('This session requires an unsupported approval or environment action. Inspect the saved state.', state)
        call_id = action.get('call_id')
        if call_id in handled:
            continue
        if action.get('name') != 'text_statistics' or not allowed or not isinstance(call_id, str):
            raise AgentError('Function tool is not explicitly allowed; no legacy plugin was executed.', state)
        arguments = action.get('arguments')
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = None
        valid = (isinstance(arguments, dict) and set(arguments) == {'text'} and
                 isinstance(arguments['text'], str) and len(arguments['text']) <= 20000)
        if len(handled) >= 10:
            raise AgentError('Function-call budget exceeded; cancel or inspect this session.', state)
        result = {'type': 'agent.session.input.tool_result', 'turn_id': state.turn_id,
                  'call_id': call_id, 'success': valid}
        if valid:
            text = arguments['text']
            result['output'] = json.dumps({'characters': len(text), 'lines': len(text.splitlines()), 'words': len(text.split())})
        else:
            result['error'] = 'Invalid text_statistics arguments; expected only text of at most 20000 characters.'
        client.beta.agents.sessions.events.create(state.session_id, events=[result])
        handled.add(call_id)
        state.progress = 'tool.text_statistics.completed' if valid else 'tool.text_statistics.rejected'


def run_task(client, prompt, model, *, session_id=None, allow_text_tool=False, run_id=None, deadline_seconds=90, on_progress=None):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise AgentError('Provide a text prompt of 1–20000 characters.')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', model):
        raise AgentError('Provide an explicit model ID.')
    if run_id is not None and not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise AgentError('Invalid local run identifier.')
    state = TurnState(session_id=session_id)
    deadline = time.monotonic() + deadline_seconds
    handled = set()
    try:
        if session_id:
            session = as_dict(client.beta.agents.sessions.retrieve(session_id))
            if session.get('status') != 'idle':
                raise AgentError('Session is not ready for follow-up; inspect or cancel it first.', state)
            prior = list(islice(client.beta.agents.sessions.turns.list(session_id, limit=100), 501))
            if len(prior) > 500:
                raise AgentError('Session turn-history limit reached; save artifacts and start a new session.', state)
            state.ignored_turn_ids = {as_dict(turn)['id'] for turn in prior}
            stream = client.beta.agents.sessions.events.stream(session_id)
        else:
            stream = client.beta.agents.sessions.create(
                agent={'model': model, 'instructions': 'Perform only the requested task. Keep your final answer concise. Use files in /workspace for deliverables.',
                       'reasoning': {'effort': 'low'}, 'multi_agent': {'enabled': False},
                       'tools': [TEXT_TOOL] if allow_text_tool else []},
                environment={'type': 'openai_hosted', 'network': {'mode': 'disabled'}},
                input=prompt, stream=True, metadata={'chuanhu_run_id': run_id} if run_id else {},
            )
        with stream as events:
            # Establish the stream before submitting follow-up input. Never
            # resubmit automatically if submission or streaming is uncertain.
            if session_id:
                client.beta.agents.sessions.events.create(session_id, events=[{
                    'type': 'agent.session.input.message',
                    'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}]}],
                }])
            for event in events:
                event = as_dict(event)
                state.accept(event)
                if event.get('type') == 'agent.session.requires_action':
                    session = as_dict(client.beta.agents.sessions.retrieve(state.session_id))
                    handle_function_actions(client, state, session, allow_text_tool, handled)
                if on_progress:
                    on_progress(state)
                if state.outcome == 'completed':
                    return state
                if time.monotonic() > deadline:
                    raise AgentError('Agents time budget exceeded; closing the stream does not cancel the turn. Inspect or explicitly cancel the saved session.', state)
    except AgentError:
        raise
    except Exception as error:
        if not state.session_id:
            state.outcome = 'not_started' if getattr(error, 'status_code', None) in (400, 401, 403, 404, 422, 429) else 'uncertain'
        raise safe_request_error(error, state) from None
    raise AgentError('Stream ended without target turn completion; reconcile saved items before resubmitting. No automatic retry.', state)


def inspect_saved(client, session_id, turn_id=None):
    """Read-only recovery; actual turn status, never idle/EOF, decides outcome."""
    try:
        session = as_dict(client.beta.agents.sessions.retrieve(session_id))
        turn = as_dict(client.beta.agents.sessions.turns.retrieve(turn_id, session_id=session_id)) if turn_id else None
        items = client.beta.agents.sessions.items.list(session_id, limit=100, order='asc')
        text = []
        for item in islice(items, 200):
            item = as_dict(item)
            if item.get('type') == 'message' and item.get('role') == 'assistant' and item.get('turn_id') == turn_id:
                text.extend(part['text'] for part in item.get('content', []) if part.get('type') == 'output_text')
        artifacts = [as_dict(item) for item in islice(client.beta.agents.sessions.artifacts.list(session_id, limit=20), 20)]
        return {'session_status': session.get('status'), 'outcome': turn.get('status') if turn else 'incomplete',
                'text': '\n'.join(text), 'artifacts': artifacts, 'required_actions': [a.get('type') for a in session.get('required_actions', [])]}
    except Exception as error:
        raise safe_request_error(error) from None


def download_artifacts(client, session_id):
    """Bounded downloads via the official API only; never follow artifact URLs."""
    output_dir = Path(tempfile.mkdtemp(prefix='chuanhu-agent-artifacts-'))
    files = []
    total = 0
    try:
        artifacts = list(islice(client.beta.agents.sessions.artifacts.list(session_id, limit=20), 20))
        for index, artifact in enumerate(artifacts):
            artifact = as_dict(artifact)
            size = artifact.get('size_bytes', 0)
            if not isinstance(size, int) or size < 0 or size > 10 * 1024 * 1024 or total + size > 50 * 1024 * 1024:
                raise AgentError('Artifact download size limit exceeded (10 MiB/file, 50 MiB total).')
            name = re.sub(r'[^A-Za-z0-9_.-]', '_', Path(artifact.get('path', 'artifact')).name).lstrip('.') or 'artifact'
            path = output_dir / (str(index + 1) + '-' + name[:120])
            received = 0
            with client.beta.agents.sessions.artifacts.with_streaming_response.content(artifact['id'], session_id=session_id) as response:
                with path.open('wb') as output:
                    for chunk in response.iter_bytes():
                        received += len(chunk)
                        if received > 10 * 1024 * 1024 or total + received > 50 * 1024 * 1024:
                            raise AgentError('Artifact download size limit exceeded.')
                        output.write(chunk)
            total += received
            files.append(str(path))
        return files
    except AgentError:
        raise
    except Exception as error:
        raise safe_request_error(error) from None


def cancel_session(client, session_id):
    """Explicit cancellation action, distinct from closing a browser/stream."""
    try:
        return client.beta.agents.sessions.events.create(session_id, events=[{'type': 'agent.session.input.cancel'}])
    except Exception as error:
        raise safe_request_error(error) from None


def find_uncertain_session(client, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise AgentError('Invalid local run identifier.')
    try:
        for session in islice(client.beta.agents.sessions.list(limit=100, order='desc'), 100):
            session = as_dict(session)
            if session.get('metadata', {}).get('chuanhu_run_id') == run_id:
                turns = client.beta.agents.sessions.turns.list(session['id'], limit=100, order='desc')
                root = next((as_dict(turn) for turn in islice(turns, 100) if as_dict(turn).get('subagent_id') is None), None)
                return session['id'], root['id'] if root else None
    except Exception as error:
        raise safe_request_error(error) from None
    raise AgentError('No matching session found among the latest 100 sessions. No input was resubmitted; retain the private run journal for operator recovery.')
