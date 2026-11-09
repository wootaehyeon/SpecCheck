import io
import json
import os
import time
from uuid import uuid4

import pytest

from speccheck_agent import desktop


def config():
    return {'version': 1, 'device_id': str(uuid4()), 'name': 'Synthetic PC',
            'backend_url': 'https://example.com', 'writer_token': 'sc_write_' + 'x' * 40,
            'interval': 30, 'security_consent': False, 'consent_version': 'monitor-v1'}


@pytest.mark.parametrize('url', ['http://example.com', 'file:///tmp/config', 'https://a:b@example.com',
                                'https://example.com/path', 'https://example.com?token=secret', 'https://example.com#fragment'])
def test_desktop_rejects_ambiguous_server_origins(url):
    with pytest.raises(ValueError):
        desktop.server_origin(url)


def test_code_redemption_sends_consent_without_long_lived_credentials(monkeypatch):
    sent = []
    result = config()
    result.pop('backend_url')
    class Response(io.BytesIO):
        pass
    class Opener:
        def open(self, request, **kwargs):
            sent.append(request)
            return Response(json.dumps(result).encode())
    monkeypatch.setattr(desktop.urllib.request, 'build_opener', lambda handler: Opener())
    connected = desktop.redeem_code('https://example.com/', 'abcd-2345')
    assert connected['backend_url'] == 'https://example.com'
    assert json.loads(sent[0].data) == {'code': 'ABCD2345', 'accepted': True}
    assert sent[0].get_header('Authorization') is None
    assert 'ABCD' not in sent[0].full_url
    with pytest.raises(desktop.PairingError):
        desktop.redeem_code('https://example.com', 'short')


@pytest.mark.skipif(os.name != 'nt', reason='Windows user-scoped DPAPI')
def test_saved_connection_is_encrypted_and_reusable(tmp_path):
    original = config()
    path = tmp_path / 'desktop-connection.dat'
    desktop.save_connection(path, original)
    assert original['writer_token'].encode() not in path.read_bytes()
    assert b'example.com' not in path.read_bytes()
    assert desktop.read_connection(path) == original
    assert not path.with_suffix('.tmp').exists()
    path.write_bytes(b'corrupted credential file')
    with pytest.raises(OSError):
        desktop.read_connection(path)


@pytest.mark.skipif(os.name != 'nt', reason='Windows desktop GUI')
def test_gui_connects_stops_and_reuses_saved_connection(tmp_path, monkeypatch):
    import tkinter as tk
    connected = config()
    redeemed = []
    collected = []
    def redeem(server, code):
        redeemed.append((server, code))
        return connected
    def watch(args, agent_config, *, connection, stop_event, on_status, on_snapshot):
        collected.append(connection)
        on_status('connected', 'Synthetic connection ready')
        on_snapshot('synthetic-gui-scan')
        stop_event.wait(3)
        return 0
    monkeypatch.setattr(desktop, 'default_server', lambda: 'https://example.com')
    monkeypatch.setattr(desktop, 'redeem_code', redeem)
    monkeypatch.setattr(desktop, 'cmd_watch', watch)
    monkeypatch.setattr(desktop, 'run_assistance', lambda *a, **kw: {
        'action': 'keep', 'text': '현재 유지', 'links': []})
    def wait(root, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            root.update()
            if predicate():
                return
            time.sleep(.02)
        pytest.fail('Desktop state did not settle')
    root = tk.Tk()
    root.withdraw()
    app = desktop.DesktopApp(root, tmp_path)
    try:
        app.code.set('ABCD-2345')
        app.start()
        wait(root, lambda: app.status.get() == 'Synthetic connection ready')
        assert app.code.get() == '' and app.path.is_file()
        assert len(redeemed) == 1 and len(collected) == 1
        app.stop()
        wait(root, lambda: str(app.start_button['state']) == 'normal')
        # Running the program again restores the encrypted credentials automatically.
        root.destroy()
        root = tk.Tk()
        root.withdraw()
        app = desktop.DesktopApp(root, tmp_path)
        wait(root, lambda: len(collected) == 2)
        assert len(redeemed) == 1
        app.stop()
        wait(root, lambda: str(app.start_button['state']) == 'normal')
        wait(root, lambda: app.assist_worker is None)
        _check_purchase_report_and_reconnection(app, root, monkeypatch)
    finally:
        app.stop_event.set()
        if app.worker:
            app.worker.join(3)
        root.destroy()


@pytest.mark.skipif(os.name != 'nt', reason='Windows elevation handoff')
def test_elevation_restarts_independently_without_passing_credentials(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tkinter import messagebox
    calls = []
    class Execute:
        def __call__(self, *args):
            assert os.environ['PYINSTALLER_RESET_ENVIRONMENT'] == '1'
            calls.append(args)
            return 42
    monkeypatch.setattr(desktop.ctypes.windll.shell32, 'ShellExecuteW', Execute())
    monkeypatch.setattr(messagebox, 'askyesno', lambda *args: True)
    monkeypatch.setenv('PYINSTALLER_RESET_ENVIRONMENT', 'original')
    destroyed = []
    app = desktop.DesktopApp.__new__(desktop.DesktopApp)
    app.home = tmp_path / 'path with spaces'
    app.root = SimpleNamespace(destroy=lambda: destroyed.append(True))
    assert app.elevate() is True
    assert destroyed == [True]
    assert calls[0][1] == 'runas'
    assert '--wait-for-parent' in calls[0][3]
    assert 'writer_token' not in calls[0][3] and 'sc_write_' not in calls[0][3]
    assert os.environ['PYINSTALLER_RESET_ENVIRONMENT'] == 'original'


def _check_purchase_report_and_reconnection(app, root, monkeypatch):
    # Reuse the connected GUI's Tcl interpreter, as a user does in one app session.
    report = {'action': 'purchase', 'text': '메모리 후보 / 슬롯 추가 확인 / 가격 미확인',
              'links': [{'label': '메모리 판매처', 'url': 'https://www.ebay.com/sch/i.html?_nkw=memory'}]}
    opened = []
    calls = []
    monkeypatch.setattr(desktop, 'default_server', lambda: 'https://example.com')
    def run(connection, **kwargs):
        calls.append(kwargs)
        return report
    monkeypatch.setattr(desktop, 'run_assistance', run)
    monkeypatch.setattr(desktop.webbrowser, 'open', opened.append)
    try:
        app.open_assistance()
        app.assistance_window.withdraw()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and app.assistance != report:
            root.update()
            time.sleep(.02)
        assert app.assistance == report and calls == [{'fetch_quotes': True}]
        assert '슬롯 추가 확인' in app.assistance_text.get('1.0', 'end')
        app.shopping_list.selection_set(0)
        app.open_shopping()
        app.open_purchase_history()
        assert opened == [report['links'][0]['url'], 'https://example.com/purchases.html']
        # A late response in the same connection must not replace a newer request.
        request_id = app.assistance_request_id
        app.assistance_request_id += 1
        app.events.put(('assistance_result', (app.assistance_generation, request_id, None, 'late failure')))
        app.drain()
        assert app.assistance == report
        previous = app.assistance_generation
        app.events.put(('paired', config()))
        app.events.put(('assistance_result', (previous, app.assistance_request_id, report, None)))
        app.drain()
        assert app.assistance is None and app.shopping_list.size() == 0
    finally:
        if app.assist_worker:
            app.assist_worker.join(3)
