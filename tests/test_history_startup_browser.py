"""Real Gradio Radio initialization must preserve an unsaved draft without clicks.

Set CHUANHU_PLAYWRIGHT_CLI to an installed playwright-cli executable to run.
The server, model and all history/config data are synthetic and isolated.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest


@pytest.mark.parametrize('model_name', ['GPT3.5 Turbo', 'OpenAI Agent'])
def test_startup_select_preserves_current_draft_without_clicks(tmp_path, model_name):
    cli = os.environ.get('CHUANHU_PLAYWRIGHT_CLI') or shutil.which('playwright-cli')
    if not cli:
        pytest.skip('Set CHUANHU_PLAYWRIGHT_CLI to run the real browser regression')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    marker = tmp_path / 'result.json'
    process_env = dict(os.environ, GRADIO_ANALYTICS_ENABLED='False')
    session = 'history-startup-' + str(port)
    with (tmp_path / 'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, __file__, '--serve', str(port), str(marker), model_name],
                                  cwd=Path(__file__).resolve().parents[1], env=process_env,
                                  stdout=log, stderr=log)
        try:
            url = f'http://127.0.0.1:{port}'
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert server.poll() is None, (tmp_path / 'server.log').read_text()
                try:
                    with urllib.request.urlopen(url, timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail('Synthetic Gradio server did not start')
            # The only browser action is navigation: no click, input or API call.
            opened = subprocess.run([cli, '-s=' + session, 'open', url], cwd=tmp_path,
                                    capture_output=True, text=True, timeout=40)
            assert opened.returncode == 0, opened.stdout + opened.stderr
            deadline = time.monotonic() + 20
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert marker.exists(), (tmp_path / 'server.log').read_text()
            result = json.loads(marker.read_text())
            assert result == {'selection': None, 'preserved': True,
                              'updates_only': True, 'history_files': 0}, result
            # Callback completion can precede the browser's initial render.
            deadline = time.monotonic() + 15
            while True:
                snapshot_path = tmp_path / 'rendered.yml'
                snapshot = subprocess.run([cli, '-s=' + session, 'snapshot', '--filename=' + str(snapshot_path)], cwd=tmp_path,
                                          capture_output=True, text=True, timeout=20)
                assert snapshot.returncode == 0, snapshot.stdout + snapshot.stderr
                rendered = snapshot_path.read_text()
                if 'Synthetic unsent input' in rendered or time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
            assert 'radio "Synthetic unsaved draft"' not in rendered
            assert 'Synthetic unsent input' in rendered
            assert rendered.count('Synthetic preserved UI value') == 22
            assert model_name in rendered
            assert '历史记录无法读取或格式无效' not in rendered
        finally:
            subprocess.run([cli, '-s=' + session, 'close'], cwd=tmp_path,
                           capture_output=True, timeout=20)
            server.terminate()
            server.wait(timeout=10)


def serve(port, marker, model_name):
    import tempfile
    from copy import deepcopy
    import gradio as gr
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from offline_models import install
    from agent_fixtures import select, request
    storage = Path(tempfile.mkdtemp(prefix='chuanhu-startup-browser-'))
    env = install(root, storage / 'history')
    env.presets.HISTORY_DIR = str(env.history_dir)
    env.agents.shared.chuanhu_path = str(storage)
    from modules.history_selection import load_history_model
    model = select(env, name=model_name)
    model.reset()
    model.history_file_path = 'Synthetic unsaved draft.json'
    model.system_prompt = 'Synthetic configured prompt'
    model.temperature = 0.37
    fields = ('history_file_path', 'history', 'chatbot', 'system_prompt', 'temperature',
              '_state', '_tool_settings', '_conversation_id')
    before = deepcopy({key: getattr(model, key, None) for key in fields})
    def automatic_selection(current, name):
        result = load_history_model(current, name, request())
        Path(marker).write_text(json.dumps({
            'selection': name,
            'preserved': result[0] is current and before == {key: getattr(current, key, None) for key in fields},
            'updates_only': len(result) == 24 and all(v == {'__type__': 'update'} for v in result[1:]),
            'history_files': len(list(env.history_dir.glob('*.json'))),
        }))
        return result
    with gr.Blocks() as app:
        state = gr.State()
        radio = gr.Radio(choices=['Synthetic saved history'], value=None)
        outputs = [state, gr.Dropdown(choices=[model_name], value=model_name)]
        outputs += [gr.Textbox(value='Synthetic preserved UI value') for _ in range(22)]
        gr.Textbox(value='Synthetic unsent input', elem_id='unsent-input')
        def initial():
            from modules.models.base_model import init_history_list
            automatic_selection(model, None)
            return model, init_history_list(model.user_name, prepend=model.history_file_path.removesuffix('.json'))
        app.load(initial, outputs=[state, radio])
        radio.input(automatic_selection, [state, radio], outputs)
    app.launch(server_name='127.0.0.1', server_port=int(port))


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '--serve':
    serve(*sys.argv[2:])
