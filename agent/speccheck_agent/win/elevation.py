"""Request Windows UAC before monitoring; cancellation never starts collection."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..config import AgentConfig


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def request_monitor_elevation(config: AgentConfig, interval: int, upload: bool) -> bool:
    # Preserve the original settings even when UAC uses a different administrator
    # account. Pass data as a JSON argument, never interpolate it into Python code.
    settings = json.dumps({
        "home": str(config.home.resolve()), "backend_url": config.backend_url,
        "device_id": config.device_id, "upload_timeout": config.upload_timeout,
    }, ensure_ascii=False)
    bootstrap = (
        "import json,sys; from pathlib import Path; "
        "from speccheck_agent.config import AgentConfig; "
        "from speccheck_agent.cli import build_parser,cmd_monitor,_force_utf8_output; "
        "_force_utf8_output(); cfg=json.loads(sys.argv[1]); cfg['home']=Path(cfg['home']); "
        "args=build_parser().parse_args(sys.argv[2:]); "
        "sys.exit(cmd_monitor(args,AgentConfig(**cfg)))"
    )
    args = ["-c", bootstrap, settings, "monitor", "--security-consent",
            "--interval", str(interval), "--elevated-child"]
    if upload:
        args.append("--upload")
    parameters = subprocess.list2cmdline(args)
    script = (
        "try { Start-Process -FilePath " + _ps_literal(sys.executable)
        + " -ArgumentList " + _ps_literal(parameters)
        + " -WorkingDirectory " + _ps_literal(str(Path(__file__).resolve().parents[2]))
        + " -Verb RunAs -WindowStyle Normal -ErrorAction Stop; exit 0 } "
        + "catch { exit 1 }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, check=False,
        )
    except OSError:
        return False
    return result.returncode == 0
