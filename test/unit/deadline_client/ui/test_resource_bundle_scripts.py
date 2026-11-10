# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import deadline.client.ui as ui_package

RESOURCES_DIR = Path(ui_package.__file__).parent / "resources"


def _embedded_bash_scripts():
    for template_path in sorted(RESOURCES_DIR.glob("*/template.yaml")):
        template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        for step in template.get("steps", []):
            for embedded_file in step.get("script", {}).get("embeddedFiles", []):
                data = embedded_file.get("data", "")
                if data.startswith("#!") and "bash" in data.splitlines()[0]:
                    yield pytest.param(
                        data,
                        id=f"{template_path.parent.name}:{step['name']}:{embedded_file['name']}",
                    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
@pytest.mark.parametrize("script", list(_embedded_bash_scripts()))
def test_embedded_bash_script_has_valid_syntax(script: str) -> None:
    result = subprocess.run(
        ["bash", "-n"], input=script, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
