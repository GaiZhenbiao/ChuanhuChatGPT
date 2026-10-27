"""Private JSON-lines bridge using the same interpreter and SDK as the app."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from modules import shared
from modules.presets import i18n
from modules.agent.connection import (AgentConnectionError, resolve_connection,
                                        worker_environment)

ROOT = Path(shared.chuanhu_path).resolve()


def connection_for_model(api_key=None, api_host=None, organization=None, project=None):
    """Capture the ordinary model's key/base and the existing app proxy scope."""
    from modules.config import config, my_api_key, retrieve_proxy
    base = shared.format_openai_host(api_host)[2] if api_host else shared.state.openai_api_base
    with retrieve_proxy():
        return resolve_connection(
            api_key=my_api_key if api_key is None else api_key, api_base=base,
            organization=organization if organization is not None else os.environ.get('OPENAI_ORG_ID', config.get('openai_organization', config.get('openai_org_id', ''))),
            project=project if project is not None else os.environ.get('OPENAI_PROJECT_ID', config.get('openai_project', config.get('openai_project_id', ''))),
            environ=dict(os.environ), credential_path=ROOT / '.env.agents')


def worker_messages(command, connection=None):
    """Yield complete messages until the worker exits; closing only detaches it.

    Remote cancellation is an explicit API command, never inferred from killing
    this local observer. The connection snapshot is not logged or persisted.
    """
    command = dict(command)
    observer_cancelled = command.pop('_observe_cancel', None)
    try:
        connection = connection if connection is not None else command.get('connection')
        if connection is None:
            connection = connection_for_model()
        command['connection'] = connection
        environment = worker_environment(connection)
    except AgentConnectionError as error:
        yield {'type': 'error', 'outcome': 'not_started', 'message': str(error)}
        return
    try:
        process = subprocess.Popen([sys.executable, '-u', '-m', 'modules.agent.worker'],
                                   cwd=ROOT, env=environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, encoding='utf-8')
    except OSError:
        yield {'type': 'error', 'outcome': 'not_started', 'message': '无法启动主项目 Python 工作进程，请检查当前运行环境；任务尚未提交。'}
        return
    messages = queue.Queue(maxsize=64)
    stopped = threading.Event()

    def enqueue(value):
        while not stopped.is_set():
            try:
                messages.put(value, timeout=1)
                return
            except queue.Full:
                pass

    def reader():
        try:
            while not stopped.is_set():
                line = process.stdout.readline()
                if not line:
                    break
                enqueue(line)
        except (OSError, ValueError):
            pass
        finally:
            enqueue(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    terminal_received = False
    snapshot = {}
    try:
        process.stdin.write(json.dumps(command, ensure_ascii=False) + '\n')
        process.stdin.close()
        while True:
            if observer_cancelled and observer_cancelled(): return
            try:
                line = messages.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                if not terminal_received:
                    yield {'type': 'error', **snapshot, 'outcome': 'incomplete',
                           'message': '本地连接已中断，云端任务状态尚未确认；请重新连接原会话查看结果，不要重复发送。'}
                break
            try:
                message = json.loads(line)
            except ValueError:
                yield {'type': 'error', **snapshot, 'outcome': 'incomplete', 'message': i18n('model.openai_agent.invalid_response')}
                break
            if not isinstance(message, dict) or message.get('type') not in ('progress', 'result', 'error', 'capabilities'):
                yield {'type': 'error', **snapshot, 'outcome': 'incomplete', 'message': i18n('model.openai_agent.invalid_response')}
                break
            snapshot.update({key: message[key] for key in ('session_id', 'turn_id', 'submission_started', 'baseline_turn_ids') if key in message})
            terminal_received = terminal_received or message['type'] in ('result', 'error', 'capabilities')
            yield message
            # A worker result is the operation boundary; process teardown must
            # not keep the UI queue open after the authoritative result.
            if message['type'] in ('result', 'error', 'capabilities'): break
    except (BrokenPipeError, OSError):
        yield {'type': 'error', **snapshot, 'outcome': 'incomplete',
               'message': '本地连接已中断，云端任务状态尚未确认；请重新连接原会话查看结果。'}
    finally:
        stopped.set()
        if not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        # Reaping a local worker is independent of the cloud operation result.
        # Stop it immediately, then close pipes/reap off the Gradio queue thread.
        if process.poll() is None:
            process.terminate()
        def reap():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            finally:
                process.stdout.close()
                thread.join(timeout=1)
        threading.Thread(target=reap, daemon=True).start()
