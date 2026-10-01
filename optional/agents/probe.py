"""One explicit synthetic integration probe; no local/user files are uploaded."""
import argparse
import json
from runtime import AgentError, create_client, read_dedicated_key, run_task


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', help='Explicitly authorize one paid official request')
    parser.add_argument('--model', default='gpt-6-astra')
    args = parser.parse_args()
    if not args.execute:
        print('Probe disabled. Pass --execute only after approving one official request.')
        return 0
    state = None
    try:
        with create_client(read_dedicated_key()) as client:
            try:
                state = run_task(client, 'Create a file named probe.txt containing exactly CHUANHU_AGENT_PROBE_OK. Read it back with the sandbox shell and report that exact content. Do not access the network or create other files.', args.model)
                print(json.dumps({'status': state.outcome, 'sandbox_marker_reported': 'CHUANHU_AGENT_PROBE_OK' in state.text, 'session_id': state.session_id, 'turn_id': state.turn_id}))
            finally:
                # Only our completed synthetic session is disposable; a partial
                # turn must be inspected/cancelled explicitly before deletion.
                if state and state.outcome == 'completed' and state.session_id:
                    try:
                        client.beta.agents.sessions.delete(state.session_id)
                        print('Synthetic test session deleted.')
                    except Exception:
                        print('Cleanup not confirmed; delete only the reported synthetic session after inspecting it.')
    except AgentError as error:
        print(str(error))
        if error.state and error.state.session_id:
            print(json.dumps({'session_id': error.state.session_id, 'turn_id': error.state.turn_id, 'status': error.state.outcome}))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
