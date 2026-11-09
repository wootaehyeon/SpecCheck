"""Build a self-contained GUI with the deployment's public origin baked in."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from speccheck_agent.desktop import server_origin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", required=True, help="Public HTTPS origin, or localhost for development")
    parser.add_argument("--sign-thumbprint", help="Optional code-signing certificate thumbprint in the Windows user certificate store")
    parser.add_argument("--signtool", default="signtool", help="Path to Windows SDK signtool.exe")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Build the Windows Agent on Windows (see windows-agent.yml).")
    origin = server_origin(args.backend_url)
    work = ROOT / "build" / "windows-agent"
    work.mkdir(parents=True, exist_ok=True)
    defaults = work / "desktop-defaults.json"
    defaults.write_text(json.dumps({"backend_url": origin}), encoding="utf-8")
    output = ROOT / "agent" / "releases"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--noupx", "--name", "SpecCheck-Agent", "--paths", str(ROOT / "agent"),
        "--add-data", str(defaults) + ";.", "--distpath", str(output), "--workpath", str(work / "work"),
        "--specpath", str(work), str(ROOT / "agent" / "desktop_entry.py")], check=True, cwd=ROOT)
    executable = output / "SpecCheck-Agent.exe"
    if args.sign_thumbprint:
        subprocess.run([args.signtool, "sign", "/sha1", args.sign_thumbprint, "/fd", "SHA256",
            "/tr", "http://timestamp.digicert.com", "/td", "SHA256", str(executable)], check=True)
        subprocess.run([args.signtool, "verify", "/pa", str(executable)], check=True)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (output / "SpecCheck-Agent.sha256").write_text(digest + "  SpecCheck-Agent.exe\n", encoding="ascii")
    (output / "build-info.json").write_text(json.dumps({"backend_url": origin, "sha256": digest,
        "python": sys.version.split()[0]}, indent=2), encoding="utf-8")
    print(f"Built {executable} ({executable.stat().st_size:,} bytes) for {origin}")


if __name__ == "__main__":
    main()
