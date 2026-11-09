'use strict';
(() => {
  const storageKey = 'speccheck.monitor.reader.v1';
  const el = (id) => document.getElementById(id);
  const text = (id, value) => { if (el(id).textContent !== String(value)) el(id).textContent = value; };
  let connection = null;
  let polling = false;
  let timer = null;
  let ready = false;
  let chartHistory = [];
  let pairing = null;
  let hasSnapshot = false;
  let reconnecting = false;
  let lastReceivedAt = 0;
  let lastPollAt = 0;
  const pairingStorageKey = 'speccheck.monitor.pairing.v1';
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const format = (value, unit, digits = 1) => finite(value) ? `${value.toFixed(digits)}${unit}` : '확인 못함';
  const moment = (value) => {
    const date = new Date(typeof value === 'number' ? value * 1000 : value);
    return Number.isNaN(date.getTime()) ? '시각 미상' : date.toLocaleString('ko-KR');
  };

  async function api(path, options = {}) {
    const headers = { ...options.headers };
    if (connection) headers.Authorization = `Bearer ${connection.reader_token}`;
    const response = await fetch(`/api/monitor/${path}`, { ...options, headers, cache: 'no-store', signal: AbortSignal.timeout(20000) });
    if (response.status === 204) return null;
    const body = await response.json();
    if (!response.ok) {
      const error = new Error(typeof body.detail === 'string' ? body.detail : '모니터링 요청에 실패했습니다.');
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function saveFile(name, data) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url; link.download = name;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function showConnection() {
    el('setupPanel').hidden = !!connection;
    el('connectionPanel').hidden = !connection || (hasSnapshot && !reconnecting);
    el('dashboardPanel').hidden = !connection || !hasSnapshot;
    el('downloadPanel').hidden = !!connection;
    text('connectedName', connection?.name || '내 PC');
    showSecurityConsent();
  }

  function forgetConnection() {
    localStorage.removeItem(storageKey); sessionStorage.removeItem(pairingStorageKey);
    connection = null; pairing = null; hasSnapshot = false; reconnecting = false; lastReceivedAt = 0;
    showConnection(); updateCode();
  }

  function showSecurityConsent() {
    const enabled = !!connection?.security_allowed;
    el('securityToggleButton').disabled = !connection || !ready;
    text('securityToggleButton', enabled ? 'Sysmon 수집 끄기' : 'Sysmon 수집 켜기');
    text('securityConsentState', enabled
      ? 'Sysmon 수집 동의: 켜짐 · 실행 파일명, 이벤트 시각, 부모 프로세스 관계를 서버에 전송하고 7일간 보관합니다.'
      : 'Sysmon 수집 동의: 꺼짐 · 새 프로세스 이벤트를 전송하지 않습니다.');
  }

  async function issueCode() {
    const current = connection;
    el('newCodeButton').disabled = true;
    try {
      const issued = await api('pairing-code', { method: 'POST' });
      if (current !== connection) return;
      pairing = { ...issued, device_id: connection.device_id, baseline_received_at: lastReceivedAt };
      sessionStorage.setItem(pairingStorageKey, JSON.stringify(pairing));
      reconnecting = hasSnapshot;
      showConnection(); updateCode();
      text('pairingProgress', '프로그램 연결 대기 중');
      text('monitorMessage', '프로그램에 연결 코드를 입력하고 ‘연결하고 시작’을 눌러주세요. 데이터가 도착하면 자동으로 표시됩니다.');
    } finally { el('newCodeButton').disabled = false; }
  }

  function updateCode() {
    text('serverOrigin', window.location.origin);
    const valid = !!pairing && !!connection && pairing.device_id === connection.device_id;
    const remaining = valid ? Math.max(0, Math.ceil(pairing.expires_at - Date.now() / 1000)) : 0;
    text('pairingCode', valid && !pairing.consumed ? pairing.code : '—');
    el('copyCodeButton').disabled = remaining === 0 || !!pairing?.consumed;
    text('codeExpiry', pairing?.consumed ? '연결 코드를 사용했습니다. 프로그램에서 수집을 시작하고 있습니다.' : remaining ? `남은 시간 ${Math.floor(remaining / 60)}분 ${String(remaining % 60).padStart(2, '0')}초 · 한 번만 사용할 수 있어요.`
      : valid ? '코드가 만료되었습니다. 새 코드를 발급해주세요.' : '새 코드 발급을 눌러 프로그램에 연결하세요.');
  }

  el('newCodeButton').addEventListener('click', async () => {
    try { await issueCode(); } catch (error) { text('monitorMessage', error.message); }
  });
  el('copyCodeButton').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(pairing.code); text('codeExpiry', '코드를 복사했습니다. 프로그램에 붙여넣어주세요.'); }
    catch { text('codeExpiry', '코드를 선택해 직접 복사해주세요.'); }
  });
  el('checkConnectionButton').addEventListener('click', refresh);

  function tableRows(id, rows, empty) {
    const body = el(id);
    body.replaceChildren();
    if (!rows.length) rows = [[empty]];
    for (const values of rows) {
      const row = document.createElement('tr');
      for (const value of values) {
        const cell = document.createElement('td'); cell.textContent = value ?? '확인 못함'; row.append(cell);
      }
      if (values.length === 1) row.firstChild.colSpan = id === 'eventBody' ? 4 : 3;
      body.append(row);
    }
  }

  function drawChart(history) {
    const chart = el('usageChart'); chart.replaceChildren();
    chartHistory = history;
    const width = Math.max(280, Math.min(900, chart.clientWidth || 900));
    chart.setAttribute('viewBox', `0 0 ${width} 200`);
    const ns = 'http://www.w3.org/2000/svg';
    for (const percent of [0, 50, 100]) {
      const line = document.createElementNS(ns, 'line');
      const y = 180 - percent * 1.6;
      for (const [key, value] of Object.entries({ x1: 40, x2: width - 10, y1: y, y2: y, stroke: '#414750' })) line.setAttribute(key, value);
      chart.append(line);
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', 0); label.setAttribute('y', y + 4); label.setAttribute('fill', '#93989e'); label.setAttribute('font-size', 12);
      label.textContent = `${percent}%`; chart.append(label);
    }
    for (const [key, color] of [['cpu_percent', '#79b8ff'], ['memory_committed_percent', '#e1b68b']]) {
      // 결측 구간을 가로질러 선을 이어 정상 값처럼 보이지 않게 한다.
      let segment = [];
      const flush = () => {
        if (segment.length) {
          const line = document.createElementNS(ns, 'polyline');
          line.setAttribute('points', segment.join(' ')); line.setAttribute('stroke', color);
          line.setAttribute('fill', 'none'); line.setAttribute('stroke-width', 3); chart.append(line);
        }
        segment = [];
      };
      history.forEach((row, i) => {
        if (!finite(row[key])) { flush(); return; }
        segment.push(`${40 + (width - 50) * i / Math.max(1, history.length - 1)},${180 - Math.max(0, Math.min(100, row[key])) * 1.6}`);
      });
      flush();
    }
    text('chartRange', history.length ? `${moment(history[0].received_at)} — ${moment(history.at(-1).received_at)}` : '아직 수집된 값이 없습니다.');
  }

  function render(latest, history, events) {
    const snapshot = latest.snapshot;
    hasSnapshot = !!snapshot;
    lastReceivedAt = latest.received_at || 0;
    if (pairing && latest.pairing_state === 'connected') {
      pairing.consumed = true;
      sessionStorage.setItem(pairingStorageKey, JSON.stringify(pairing));
    }
    if (hasSnapshot && (!reconnecting || (latest.pairing_state === 'connected' && lastReceivedAt >= latest.paired_at))) {
      reconnecting = false;
      pairing = null;
      sessionStorage.removeItem(pairingStorageKey);
    }
    connection.security_allowed = latest.security_allowed;
    showConnection(); updateCode();
    text('connectedName', latest.name);
    if (!snapshot) {
      const collecting = latest.pairing_state === 'connected' || (latest.pairing_state === 'none' && latest.agent_connected);
      text('connectionStatus', collecting ? '첫 데이터 수집 중' : '프로그램 연결 대기');
      text('pairingProgress', collecting ? '프로그램이 연결되었습니다. 첫 데이터를 기다리고 있어요. 수집이 시작되지 않으면 프로그램의 안내를 확인해주세요.' : '프로그램에 코드를 입력하고 ‘연결하고 시작’을 눌러주세요.');
      return;
    }
    const elapsed = Math.max(0, Date.now() / 1000 - latest.received_at);
    text('connectionStatus', elapsed < 120 ? '수신 중' : '수신 중단');
    text('lastSeen', `마지막 수신 ${moment(latest.received_at)} · ${Math.round(elapsed)}초 전`);
    text('monitorMessage', elapsed < 120 ? '실제 PC에서 수신한 값입니다. 이 화면은 10초마다 갱신됩니다. Agent는 기본 30초마다 수집하며 하드웨어 사양은 5분마다 갱신합니다.' : '새 자료가 도착하지 않고 있습니다. 마지막 수신 자료를 표시합니다. Agent 실행 상태와 네트워크를 확인해주세요.');
    const metrics = latest.metrics || {};
    text('cpuMetric', format(metrics.cpu_percent, '%'));
    text('memoryMetric', format(finite(metrics.memory_available_mb) ? metrics.memory_available_mb / 1024 : null, ' GB'));
    text('diskMetric', format(metrics.disk_queue, ''));
    text('temperatureMetric', format(metrics.temperature_c, ' °C'));
    const hardware = snapshot.sections?.hardware?.data || {};
    const hardwareList = el('hardwareList'); hardwareList.replaceChildren();
    for (const [label, value] of [
      ['CPU', hardware.cpu?.map((item) => item.name).filter(Boolean).join(', ')],
      ['GPU', hardware.gpu?.map((item) => item.name).filter(Boolean).join(', ')],
      ['RAM', format(hardware.memory?.total_gb, ' GB')], ['OS', hardware.os?.caption],
      ['보드', hardware.motherboard?.product],
    ]) {
      const title = document.createElement('dt'); title.textContent = label;
      const detail = document.createElement('dd'); detail.textContent = value || '확인 못함'; hardwareList.append(title, detail);
    }
    const performance = snapshot.sections?.performance?.data || {};
    tableRows('processBody', (performance.top_processes || []).map((item) => [item.name, format(item.cpu_percent, '%'), format(item.memory_mb, ' MB')]), '수집된 프로세스가 없습니다.');
    const diagnosis = latest.diagnosis || {};
    text('coverageText', Object.entries(snapshot.sections || {}).map(([name, section]) => `${name}: ${section.status}`).join(' / '));
    const findings = el('findingsList'); findings.replaceChildren();
    for (const finding of diagnosis.findings || []) {
      const item = document.createElement('article'); item.className = 'monitor-finding';
      const title = document.createElement('strong'); title.textContent = `${finding.title} · ${finding.severity}`;
      const summary = document.createElement('p'); summary.textContent = finding.summary;
      const action = document.createElement('p'); action.textContent = finding.action_detail || '';
      item.append(title, summary, action);
      if (finding.recommended_action === 'purchase') {
        const purchase = document.createElement('a');
        purchase.className = 'btn btn-primary';
        purchase.href = `purchase.html?rule=${encodeURIComponent(finding.rule_id)}`;
        purchase.textContent = window.SpecCheckPurchase.profile(finding.rule_id).label;
        purchase.addEventListener('click', () => window.SpecCheckPurchase.remember(finding, hardware));
        item.append(purchase);
      }
      findings.append(item);
    }
    if (!findings.childElementCount) findings.textContent = diagnosis.unavailable ? '일부 자료의 형식 때문에 진단을 계산하지 못했습니다.' : '확보된 수집 항목에서 규칙이 감지한 이상 징후가 없습니다. 수집하지 못한 항목의 정상 여부는 판단하지 않습니다.';
    const security = snapshot.sections?.security;
    text('securityState', security ? `수집 상태: ${security.status}${security.error ? ` · ${security.error}` : ''}${security.data?.log_gap ? ' · 로그 누락 가능성 있음' : ''}${security.data?.truncated ? ' · 남은 이벤트 처리 중' : ''}` : 'Sysmon 프로세스 이력 수집을 사용하지 않고 있습니다.');
    const names = { 1: '시작', 5: '종료', 25: '변조 이벤트', 255: 'Sysmon 오류' };
    tableRows('eventBody', events.map((item) => [moment(item.occurred_at), names[item.event_id] || item.event_id, item.image || '미상', item.parent_image || '—']), '수집된 Sysmon 이벤트가 없습니다.');
    drawChart(history);
  }

  async function refresh() {
    if (!connection || polling) return;
    polling = true;
    const current = connection;
    try {
      const [latest, history, events] = await Promise.all([api('latest'), api('history'), api('process-events')]);
      if (connection === current) render(latest, history, events);
    } catch (error) {
      if (connection !== current) return;
      if (error.status === 401) {
        forgetConnection();
        text('connectionStatus', '다시 연결 필요');
        text('monitorMessage', '연결이 만료되었거나 해제되었습니다. 새 연결 코드를 받아주세요.');
      } else {
        text('connectionStatus', '연결 확인 필요'); text('monitorMessage', error.message);
      }
    } finally { polling = false; }
  }

  el('pairButton').addEventListener('click', async () => {
    if (!ready || !el('basicConsent').checked) { text('monitorMessage', '수집 항목과 서버 전송에 먼저 동의해주세요.'); return; }
    el('pairButton').disabled = true;
    try {
      connection = await api('pair', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: el('deviceName').value || '내 PC', accepted: true, security_accepted: el('securityConsent').checked }) });
      hasSnapshot = false; lastReceivedAt = 0;
      localStorage.setItem(storageKey, JSON.stringify(connection)); showConnection();
      await issueCode(); await refresh();
    } catch (error) { text('monitorMessage', error.message); }
    finally { el('pairButton').disabled = false; }
  });
  el('configButton').addEventListener('click', async () => {
    try { await issueCode(); el('connectionPanel').scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (error) { text('monitorMessage', error.message); }
  });
  el('securityToggleButton').addEventListener('click', async () => {
    if (!connection || !ready) return;
    const accepted = !connection.security_allowed;
    const prompt = accepted
      ? 'Sysmon 실행 파일명·이벤트 시각·부모 프로세스 관계를 이 서버에 전송하고 7일간 보관하는 데 동의하나요? 명령줄·전체 경로·사용자 이름은 보내지 않습니다. 새 코드를 프로그램에 입력하면 관리자 실행을 안내합니다.'
      : '새 Sysmon 이벤트 전송을 끌까요? 기존 서버 이력은 보관 기간까지 유지됩니다. 새 코드를 프로그램에 입력해주세요.';
    if (!window.confirm(prompt)) return;
    el('securityToggleButton').disabled = true;
    try {
      const settings = await api('security-consent', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accepted }) });
      connection.security_allowed = settings.security_allowed;
      localStorage.setItem(storageKey, JSON.stringify(connection));
      showSecurityConsent();
      await issueCode();
      text('monitorMessage', accepted
        ? 'Sysmon 수집을 켰습니다. 프로그램에서 수집을 중지한 후 새 코드를 입력하세요. 관리자 권한과 Sysmon 사전 설치가 필요합니다.'
        : 'Sysmon 수집을 껐습니다. 프로그램에서 수집을 중지한 후 새 코드를 입력하세요.');
    } catch (error) { text('monitorMessage', error.message); }
    finally { showSecurityConsent(); }
  });
  el('backupButton').addEventListener('click', () => saveFile('speccheck-reader.json', { version: 1, ...connection }));
  el('restoreReader').addEventListener('change', async (event) => {
    try {
      const imported = JSON.parse(await event.target.files[0].text());
      if (typeof imported.reader_token !== 'string' || !imported.reader_token.startsWith('sc_read_')) throw new Error('조회키 백업 파일이 아닙니다.');
      const previous = connection; connection = imported;
      try { await api('latest'); } catch (error) { connection = previous; throw error; }
      hasSnapshot = false; pairing = null; reconnecting = false;
      localStorage.setItem(storageKey, JSON.stringify(connection)); showConnection(); await refresh();
    } catch (error) { text('monitorMessage', error.message); }
  });
  el('refreshButton').addEventListener('click', refresh);
  async function disconnect() {
    if (!window.confirm('이 PC의 서버 이력과 연결키를 삭제합니다. 먼저 Agent를 중단해주세요. 로컬 원본은 유지됩니다. 삭제할까요?')) return;
    try {
      await api('connection', { method: 'DELETE' });
      forgetConnection();
      text('connectionStatus', '연결 해제'); text('monitorMessage', '서버 이력과 연결키를 삭제했습니다.');
    } catch (error) { text('monitorMessage', error.message); }
  }
  el('disconnectButton').addEventListener('click', disconnect);
  el('cancelConnectionButton').addEventListener('click', disconnect);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void refresh(); });
  void (async () => {
    try {
      connection = JSON.parse(localStorage.getItem(storageKey) || 'null');
      pairing = JSON.parse(sessionStorage.getItem(pairingStorageKey) || 'null');
      if (pairing?.device_id !== connection?.device_id) pairing = null;
      reconnecting = !!pairing;
      showConnection(); updateCode();
      const status = await api('status'); ready = status.enabled;
      el('pairButton').disabled = !ready;
      const downloadAvailable = status.agent_download_available;
      for (const link of [el('downloadAgent'), el('downloadAgentAgain')]) {
        link.setAttribute('aria-disabled', String(!downloadAvailable));
        if (!downloadAvailable) link.removeAttribute('href');
      }
      if (!downloadAvailable) {
        el('downloadAgent').removeAttribute('href');
        text('downloadMessage', 'Windows 프로그램을 준비 중입니다. 준비가 끝나면 여기에서 다운로드할 수 있습니다.');
      }
      text('connectionStatus', ready ? '연결 준비 완료' : '서버 설정 필요');
      text('monitorMessage', ready ? 'Windows 프로그램을 실행한 후 연결 코드를 입력해주세요. 연결되면 PC 상태가 자동으로 표시됩니다.' : '모니터링 서비스가 아직 준비되지 않았습니다. 잠시 후 다시 확인해주세요.');
      if (connection && ready) await refresh();
      timer = setInterval(() => {
        if (!document.hidden && ready && Date.now() - lastPollAt >= (hasSnapshot && !reconnecting ? 10000 : 3000)) {
          lastPollAt = Date.now(); void refresh();
        }
      }, 1000);
    } catch (error) { text('monitorMessage', error.message); }
  })();
  const codeTimer = setInterval(() => { if (!document.hidden) updateCode(); }, 1000);
  window.addEventListener('pagehide', () => { clearInterval(timer); clearInterval(codeTimer); });
  window.addEventListener('pageshow', (event) => { if (event.persisted) window.location.reload(); });
  window.addEventListener('resize', () => drawChart(chartHistory));
})();
