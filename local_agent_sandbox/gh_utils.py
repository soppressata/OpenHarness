import shlex
import subprocess
from typing import List, Union


def gh(args: Union[str, List[str]]) -> str:
    """Execute a GitHub CLI command via subprocess and return output."""
    if isinstance(args, str):
        cmd = ["gh"] + shlex.split(args)
    else:
        cmd = ["gh"] + list(args)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.stdout.strip()
    except Exception:
        return ""
