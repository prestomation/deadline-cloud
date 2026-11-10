# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import shutil
import subprocess
import sys
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


def test_embedded_bash_scripts_are_found() -> None:
    ids = [param.id for param in _embedded_bash_scripts()]
    assert "blender_example_bundle:RenderBlender:run" in ids


# On Windows, bash may resolve to the WSL launcher, which fails without a distro.
@pytest.mark.skipif(
    sys.platform.startswith("win") or shutil.which("bash") is None,
    reason="Needs a native bash",
)
@pytest.mark.parametrize("script", list(_embedded_bash_scripts()))
def test_embedded_bash_script_has_valid_syntax(script: str) -> None:
    result = subprocess.run(
        ["bash", "-n"], input=script.encode("utf-8"), capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
