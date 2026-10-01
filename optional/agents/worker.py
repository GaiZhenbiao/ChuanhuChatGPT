"""JSON-lines bridge for the plugin's dedicated subprocess. No core imports."""
import json
import sys
import re
from runtime import AgentError, create_client, read_dedicated_key, run_task, inspect_saved, cancel_session, download_artifacts, find_uncertain_session


def emit(kind, **data):
    print(json.dumps({'type': kind, **data}, ensure_ascii=False), flush=True)


def main():
    state = None
    try:
        command = json.loads(sys.stdin.readline(100000))
        action = command.get('action')
        if action == 'capabilities':
            import openai
            with create_client('offline-check') as client:
                emit('capabilities', sdk_version=openai.__version__, available=hasattr(client.beta, 'agents'))
            return
        if action not in ('run', 'inspect', 'cancel', 'download', 'delete', 'recover_unknown'):
            raise AgentError('Unknown worker action.')
        session_id = command.get('session_id')
        if session_id and not re.fullmatch(r'sess_[A-Za-z0-9_-]{1,150}', session_id):
            raise AgentError('Invalid session identifier.')
        if action not in ('run', 'recover_unknown') and not session_id:
            raise AgentError('No session to manage.')
        with create_client(read_dedicated_key()) as client:
            if action == 'run':
                def progress(value):
                    emit('progress', session_id=value.session_id, turn_id=value.turn_id,
                         outcome=value.outcome, progress=value.progress, text=value.text)
                state = run_task(client, command.get('prompt'), command.get('model'), session_id=session_id,
                                 allow_text_tool=command.get('allow_text_tool') is True, run_id=command.get('run_id'), on_progress=progress)
                emit('result', session_id=state.session_id, turn_id=state.turn_id, outcome=state.outcome, text=state.text)
            elif action == 'recover_unknown':
                session_id, turn_id = find_uncertain_session(client, command.get('run_id'))
                result = inspect_saved(client, session_id, turn_id)
                emit('result', session_id=session_id, turn_id=turn_id, **result)
            elif action == 'inspect':
                result = inspect_saved(client, session_id, command.get('turn_id'))
                emit('result', session_id=session_id, turn_id=command.get('turn_id'), **result)
            elif action == 'cancel':
                cancel_session(client, session_id)
                emit('result', session_id=session_id, outcome='cancel_requested', text='Cancellation submitted; inspect to confirm the target turn stopped.')
            elif action == 'download':
                emit('result', session_id=session_id, files=download_artifacts(client, session_id))
            elif action == 'delete':
                session = client.beta.agents.sessions.retrieve(session_id)
                if session.status != 'idle':
                    raise AgentError('Cancel and inspect an active session before deleting it.')
                client.beta.agents.sessions.delete(session_id)
                emit('result', outcome='deleted')
    except AgentError as error:
        snapshot = error.state or state
        emit('error', message=str(error), session_id=snapshot.session_id if snapshot else None,
             turn_id=snapshot.turn_id if snapshot else None, outcome=snapshot.outcome if snapshot else 'incomplete')
    except Exception as error:
        # Never surface exception bodies, request headers, argument values, or
        # SDK logs to the host process/browser.
        from runtime import safe_request_error
        emit('error', message=str(safe_request_error(error)))

if __name__ == '__main__':
    main()
