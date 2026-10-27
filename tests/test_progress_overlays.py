"""Offline hidden-progress selector contract; actual computed styles require QA."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_hidden_generation_overlay_selector_excludes_visible_progress():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the selector contract')
    result = subprocess.run(
        [node, 'tests/javascript/progress-overlays.test.cjs'],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
