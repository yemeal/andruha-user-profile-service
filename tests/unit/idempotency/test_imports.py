import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "app.application.ports.idempotency.durable_execution",
        "app.application.idempotency.middleware",
        "app.application.idempotency.codec",
        "app.application.dispatching.result_mode",
        "app.application.dispatching.bus",
        "app.application.dispatching.registry",
    ],
)
def test_public_modules_can_be_imported_independently(module):
    source = Path(__file__).resolve().parents[3] / "src"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import {module}",
        ],
        env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
