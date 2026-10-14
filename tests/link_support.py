"""Create a directory link for tests: a junction on Windows, a symlink elsewhere. Returns False when the host refuses."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def make_link(link: Path, target: Path) -> bool:
    try:
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)
            return result.returncode == 0
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False
