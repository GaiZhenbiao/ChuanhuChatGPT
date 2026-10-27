"""Offline DOM regression for attachment-only sends through native Gradio UI."""
from pathlib import Path
import shutil
import subprocess

import gradio


def test_file_only_send_and_native_enter_controls():
    root = Path(__file__).resolve().parents[2]
    textbox_source = Path(gradio.__file__).parent / '_frontend_code/textbox/shared/Textbox.svelte'
    assert textbox_source.is_file(), 'The installed Gradio Textbox source is required for this UI regression'
    result = subprocess.run(
        [shutil.which('node') or 'node', 'tests/javascript/agent-file-only-send.test.cjs', str(textbox_source)],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
