"""真实本地子进程终态回收不占用Gradio队列，不调用网络。"""
import os
import subprocess
import sys
import time
from modules.agent import transport


def test_result_returns_before_unresponsive_worker_is_reaped(monkeypatch):
    original = subprocess.Popen
    processes = []
    def spawn(*args, **kwargs):
        process = original([sys.executable, '-u', '-c',
            'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print(\'{"type":"result","outcome":"completed"}\',flush=True); time.sleep(30)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8')
        processes.append(process)
        return process
    monkeypatch.setattr(transport.subprocess, 'Popen', spawn)
    monkeypatch.setattr(transport, 'worker_environment', lambda connection: dict(os.environ))
    started = time.monotonic()
    try:
        result = list(transport.worker_messages({'action':'inspect'}, connection={}))
        assert result == [{'type':'result','outcome':'completed'}]
        assert time.monotonic() - started < 1
    finally:
        for process in processes:
            if process.poll() is None: process.kill()
            process.wait(timeout=3)
