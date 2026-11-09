"""Windows GUI: enter a one-time code, keep credentials in the user's DPAPI vault."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from .config import AgentConfig
from .watch import NoRedirect, cmd_watch, validate_connection
from .win.cim import is_elevated, is_windows


class PairingError(ValueError):
    """An error safe to show to the person connecting this PC."""


def server_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not parsed.hostname or (parsed.scheme != "https" and not (local and parsed.scheme == "http")):
        raise ValueError("웹페이지의 HTTPS 서버 주소를 입력해주세요.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ValueError("서버 주소는 경로나 로그인 정보 없이 입력해주세요.")
    return value


def default_server() -> str:
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "desktop-defaults.json"
    if bundled.is_file():
        return server_origin(json.loads(bundled.read_text(encoding="utf-8"))["backend_url"])
    return server_origin(os.environ.get("SPECCHECK_BACKEND_URL", "http://127.0.0.1:8000"))


def redeem_code(server: str, code: str) -> dict:
    server = server_origin(server)
    code = code.strip().upper().replace("-", "").replace(" ", "")
    if not re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", code):
        raise PairingError("웹에 표시된 8자리 연결 코드를 입력해주세요.")
    request = urllib.request.Request(server + "/api/monitor/redeem",
        data=json.dumps({"code": code, "accepted": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            config = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise PairingError("연결 시도가 많습니다. 10분 후 다시 시도해주세요.") from None
        if exc.code in (400, 422):
            raise PairingError("코드가 올바르지 않거나 만료되었습니다. 웹에서 새 코드를 발급해주세요.") from None
        raise PairingError("연결을 완료하지 못했습니다. 서버 상태를 확인해주세요.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PairingError("서버에 연결할 수 없습니다. 인터넷 연결과 서버 주소를 확인해주세요.") from None
    config["backend_url"] = server
    return validate_connection(config)


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, *, decrypt=False) -> bytes:
    if os.name != "nt":
        raise OSError("연결 정보 저장은 Windows에서만 지원합니다.")
    from ctypes import wintypes
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        # CRYPTPROTECT_UI_FORBIDDEN; the Windows user account owns the encryption key.
        ok = crypt32.CryptProtectData(ctypes.byref(source), "SpecCheck connection", None, None, None, 1, ctypes.byref(result))
    if not ok:
        raise OSError("Windows가 저장된 연결 정보를 열지 못했습니다. 새 코드로 다시 연결해주세요.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(ctypes.cast(result.data, wintypes.HLOCAL))


def save_connection(path: Path, config: dict) -> None:
    encrypted = _crypt(json.dumps(validate_connection(dict(config)), ensure_ascii=False).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(path)


def read_connection(path: Path) -> dict:
    return validate_connection(json.loads(_crypt(path.read_bytes(), decrypt=True).decode("utf-8")))


class DesktopApp:
    def __init__(self, root, home: Path):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.home = root, home
        self.path = home / "desktop-connection.dat"
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.connection = None
        self.closing = False
        root.title("SpecCheck · 내 PC 연결")
        root.geometry("540x660")
        root.minsize(480, 640)
        root.configure(bg="#111827")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#d1d5db", font=("맑은 고딕", 10))
        style.configure("Title.TLabel", foreground="#f9fafb", font=("맑은 고딕", 23, "bold"))
        style.configure("TButton", font=("맑은 고딕", 11), padding=10)
        frame = ttk.Frame(root, padding=28)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="SpecCheck", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="웹의 연결 코드를 입력하면 PC 상태를 확인할 수 있어요.", wraplength=450).pack(anchor="w", pady=(8, 24))
        ttk.Label(frame, text="연결 코드").pack(anchor="w")
        self.code = tk.StringVar()
        self.entry = ttk.Entry(frame, textvariable=self.code, font=("Consolas", 24), justify="center")
        self.entry.pack(fill="x", pady=(8, 12), ipady=6)
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda _: self.start())
        self.server = tk.StringVar(value=default_server())
        advanced = ttk.Frame(frame)
        self.server_label = ttk.Label(advanced, text="웹페이지의 서버 주소")
        self.server_label.pack(anchor="w")
        self.server_entry = ttk.Entry(advanced, textvariable=self.server)
        self.server_entry.pack(fill="x", pady=6)
        self.advanced_visible = False
        def toggle_server():
            self.advanced_visible = not self.advanced_visible
            if self.advanced_visible:
                advanced.pack(fill="x", before=self.consent, pady=(0, 8))
            else:
                advanced.pack_forget()
        ttk.Button(frame, text="서버 주소 확인·변경", command=toggle_server).pack(anchor="w", pady=(0, 10))
        self.consent = ttk.Label(frame, text="‘연결하고 시작’을 누르면 웹에서 동의한 하드웨어 사양, 자원 사용량과 상위 프로세스 이름을 수집·전송합니다. Sysmon 이력은 웹에서 별도로 동의한 경우에만 수집합니다.", wraplength=450)
        self.consent.pack(anchor="w", pady=(0, 14))
        self.start_button = ttk.Button(frame, text="연결하고 시작", command=self.start)
        self.start_button.pack(fill="x")
        self.status = tk.StringVar(value="웹에서 코드를 발급한 후 입력해주세요. 코드는 10분간 유효합니다.")
        ttk.Label(frame, textvariable=self.status, wraplength=450).pack(anchor="w", pady=16)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.stop_button = ttk.Button(row, text="수집 중지", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.web_button = ttk.Button(row, text="웹에서 확인", command=self.open_web)
        self.web_button.pack(side="right")
        ttk.Label(frame, text="창을 닫으면 수집이 중단됩니다. 다음 실행 시 저장된 연결을 사용합니다.", wraplength=450).pack(anchor="w", pady=(16, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.drain)
        if self.path.is_file():
            try:
                self.connection = read_connection(self.path)
                self.server.set(self.connection["backend_url"])
                self.status.set("저장된 PC 연결을 사용합니다.")
                root.after(200, self.start)
            except (OSError, ValueError, KeyError, TypeError):
                self.status.set("저장된 연결을 열지 못했습니다. 웹에서 새 코드를 발급해주세요.")

    def open_web(self):
        try:
            webbrowser.open(server_origin(self.server.get()) + "/monitor.html")
        except ValueError as exc:
            self.status.set(str(exc))

    def set_busy(self, busy):
        self.start_button.configure(state="disabled" if busy else "normal")
        self.entry.configure(state="disabled" if busy else "normal")
        self.server_entry.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="normal" if busy else "disabled")

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            server = server_origin(self.server.get())
        except ValueError as exc:
            self.status.set(str(exc))
            return
        code = self.code.get().strip()
        if not code and self.connection is None:
            self.status.set("웹에 표시된 연결 코드를 입력해주세요.")
            return
        if not code and self.connection and self.connection["backend_url"] != server:
            self.status.set("서버를 변경하려면 해당 웹페이지에서 새 코드를 발급해주세요.")
            return
        self.stop_event.clear()
        self.set_busy(True)
        self.status.set("PC를 연결하고 있습니다…")
        def run():
            try:
                config = redeem_code(server, code) if code else self.connection
                if code:
                    save_connection(self.path, config)
                self.events.put(("paired", config))
                if config.get("security_consent") and not is_elevated():
                    self.events.put(("elevation", "Sysmon 수집에 관리자 권한이 필요합니다."))
                    return
                args = argparse.Namespace(consent=True, security_consent=config.get("security_consent", False), once=False)
                result = cmd_watch(args, AgentConfig(home=self.home), connection=config,
                    stop_event=self.stop_event, on_status=lambda state, message: self.events.put((state, message)))
                if result:
                    self.events.put(("error", "수집이 중단되었습니다. 권한과 Sysmon 설치 상태를 확인하세요. 연결키가 만료되었다면 웹에서 새 코드를 발급해주세요."))
            except PairingError as exc:
                self.events.put(("error", str(exc)))
            except (ValueError, OSError, KeyError, TypeError):
                # Never expose raw responses, tokens or local paths in the GUI.
                self.events.put(("error", "연결하지 못했습니다. 코드·서버 주소·인터넷 연결을 확인하고 다시 시도해주세요."))
            except Exception:
                self.events.put(("error", "PC 정보를 수집하지 못했습니다. 프로그램을 다시 실행해주세요."))
            finally:
                self.events.put(("stopped", None))
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.status.set("수집을 중지하고 있습니다…")
        self.stop_button.configure(state="disabled")

    def close(self):
        self.closing = True
        if self.worker and self.worker.is_alive():
            self.stop()
        else:
            self.root.destroy()

    def elevate(self):
        from tkinter import messagebox
        if not messagebox.askyesno("관리자 권한 필요", "웹에서 Sysmon 수집을 선택했습니다. 관리자 권한으로 다시 시작할까요?\nSysmon은 PC에 미리 설치되어 있어야 합니다."):
            self.status.set("웹에서 Sysmon 수집을 끄고 새 코드로 연결하거나, 관리자 권한으로 다시 실행해주세요.")
            return False
        arguments = ["--home", str(self.home), "--wait-for-parent", str(os.getpid())]
        if not getattr(sys, "frozen", False):
            arguments = ["-m", "speccheck_agent.desktop", *arguments]
        from ctypes import wintypes
        execute = ctypes.windll.shell32.ShellExecuteW
        execute.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
        execute.restype = wintypes.HINSTANCE
        previous_reset = os.environ.get("PYINSTALLER_RESET_ENVIRONMENT")
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        try:
            result = execute(None, "runas", sys.executable,
                subprocess.list2cmdline(arguments), None, 1)
        finally:
            if previous_reset is None:
                os.environ.pop("PYINSTALLER_RESET_ENVIRONMENT", None)
            else:
                os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = previous_reset
        if not result or result <= 32:
            self.status.set("관리자 실행을 취소했습니다. 다시 수집을 시작할 수 있습니다.")
            return False
        else:
            self.root.destroy()
            return True

    def drain(self):
        elevation = False
        try:
            while True:
                state, value = self.events.get_nowait()
                if state == "paired":
                    self.connection = value
                    self.code.set("")
                elif state == "elevation":
                    elevation = True
                elif state == "stopped":
                    self.set_busy(False)
                    self.start_button.configure(text="수집 시작 / 새 코드로 연결")
                    if self.closing:
                        self.root.destroy()
                        return
                    if self.stop_event.is_set():
                        self.status.set("수집을 중지했습니다. 저장된 연결로 다시 시작할 수 있습니다.")
                else:
                    self.status.set(value)
        except queue.Empty:
            pass
        if elevation:
            if self.elevate():
                return
        self.root.after(100, self.drain)


def main():
    import tkinter as tk
    from tkinter import messagebox
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=AgentConfig().home)
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--wait-for-parent", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.wait_for_parent and os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        parent = kernel.OpenProcess(0x00100000, False, args.wait_for_parent)
        if parent:
            kernel.WaitForSingleObject(parent, 5000)
            kernel.CloseHandle(parent)
    root = tk.Tk()
    if not is_windows():
        root.withdraw()
        messagebox.showerror("SpecCheck", "Windows PC에서 실행해주세요.")
        root.destroy()
        return
    # Each user runs one Agent, preventing duplicate collection and code redemption.
    mutex = None
    if not args.smoke_test:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        mutex = kernel.CreateMutexW(None, False, "Local\\SpecCheck-" + hashlib.sha256(str(args.home.resolve()).encode()).hexdigest()[:24])
        if not mutex:
            root.withdraw()
            messagebox.showerror("SpecCheck", "프로그램 실행 상태를 확인하지 못했습니다. 다시 실행해주세요.")
            root.destroy()
            return
        if ctypes.get_last_error() == 183:
            root.withdraw()
            messagebox.showinfo("SpecCheck", "SpecCheck가 이미 실행 중입니다. 열려 있는 프로그램을 확인해주세요.")
            root.destroy()
            return
    try:
        if args.smoke_test:
            # A packaged GUI/runtime check must never collect or read existing credentials.
            import tempfile
            with tempfile.TemporaryDirectory() as temp:
                DesktopApp(root, Path(temp))
                root.after(1200, root.destroy)
                root.mainloop()
        else:
            DesktopApp(root, args.home)
            root.mainloop()
    finally:
        if mutex:
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
