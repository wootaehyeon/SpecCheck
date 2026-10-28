'use strict';
(() => {
  const storageKey = 'speccheck.monitor.reader.v1';
  const el = (id) => document.getElementById(id);
  const text = (id, value) => { el(id).textContent = value; };
  let connection = null;
  let polling = false;
  let timer = null;
  let ready = false;
  let chartHistory = [];
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
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '모니터링 요청에 실패했습니다.');
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
    el('dashboardPanel').hidden = !connection;
    text('connectedName', connection?.name || '내 PC');
    showSecurityConsent();
  }

  function showSecurityConsent() {
    const enabled = !!connection?.security_allowed;
    el('securityToggleButton').disabled = !connection || !ready;
    text('securityToggleButton', enabled ? 'Sysmon 수집 끄기' : 'Sysmon 수집 켜기');
    text('securityConsentState', enabled
      ? 'Sysmon 수집 동의: 켜짐 · 실행 파일명, 이벤트 시각, 부모 프로세스 관계를 서버에 전송하고 7일간 보관합니다.'
      : 'Sysmon 수집 동의: 꺼짐 · 새 프로세스 이벤트를 전송하지 않습니다.');
  }

  async function downloadConfig() {
    const config = await api('agent-config', { method: 'POST' });
    saveFile('speccheck-monitor.json', { ...config, backend_url: window.location.origin });
    text('monitorMessage', '연결 설정을 저장했습니다. Agent ZIP의 압축을 푼 폴더에 이 파일을 넣고 Start-SpecCheck.cmd를 실행하세요. 새 설정을 받으면 이전 전송키는 폐기됩니다.');
  }

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
    connection.security_allowed = latest.security_allowed;
    showSecurityConsent();
    text('connectedName', latest.name);
    if (!snapshot) {
      text('connectionStatus', 'Agent 대기');
      text('lastSeen', '연결 설정 저장 후 Windows PC에서 Agent를 실행해주세요.');
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
    try {
      const [latest, history, events] = await Promise.all([api('latest'), api('history'), api('process-events')]);
      render(latest, history, events);
    } catch (error) {
      text('connectionStatus', '연결 확인 필요'); text('monitorMessage', error.message);
    } finally { polling = false; }
  }

  el('pairButton').addEventListener('click', async () => {
    if (!ready || !el('basicConsent').checked) { text('monitorMessage', '수집 항목과 서버 전송에 먼저 동의해주세요.'); return; }
    el('pairButton').disabled = true;
    try {
      connection = await api('pair', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: el('deviceName').value || '내 PC', accepted: true, security_accepted: el('securityConsent').checked }) });
      localStorage.setItem(storageKey, JSON.stringify(connection)); showConnection();
      await downloadConfig(); await refresh();
    } catch (error) { text('monitorMessage', error.message); }
    finally { el('pairButton').disabled = false; }
  });
  el('configButton').addEventListener('click', async () => {
    if (!window.confirm('새 연결 설정을 저장하면 이전 Agent 전송키가 폐기됩니다. 새 설정으로 Agent를 다시 실행할까요?')) return;
    try { await downloadConfig(); } catch (error) { text('monitorMessage', error.message); }
  });
  el('securityToggleButton').addEventListener('click', async () => {
    if (!connection || !ready) return;
    const accepted = !connection.security_allowed;
    const prompt = accepted
      ? 'Sysmon 실행 파일명·이벤트 시각·부모 프로세스 관계를 이 서버에 전송하고 7일간 보관하는 데 동의하나요? 명령줄·전체 경로·사용자 이름은 보내지 않습니다. 새 설정을 저장한 뒤 Agent를 관리자 권한으로 다시 실행해야 합니다.'
      : '새 Sysmon 이벤트 전송을 끌까요? 기존 서버 이력은 보관 기간까지 유지됩니다. 새 설정을 저장한 뒤 Agent를 다시 실행하세요.';
    if (!window.confirm(prompt)) return;
    el('securityToggleButton').disabled = true;
    try {
      const settings = await api('security-consent', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accepted }) });
      connection.security_allowed = settings.security_allowed;
      localStorage.setItem(storageKey, JSON.stringify(connection));
      showSecurityConsent();
      await downloadConfig();
      text('monitorMessage', accepted
        ? 'Sysmon 수집을 켜고 새 연결 설정을 저장했습니다. 기존 Agent를 중단하고 speccheck-monitor.json을 교체한 뒤 관리자 권한으로 실행하세요.'
        : 'Sysmon 수집을 껐습니다. 기존 Agent를 중단하고 새 연결 설정으로 다시 실행하세요.');
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
      localStorage.setItem(storageKey, JSON.stringify(connection)); showConnection(); await refresh();
    } catch (error) { text('monitorMessage', error.message); }
  });
  el('refreshButton').addEventListener('click', refresh);
  el('disconnectButton').addEventListener('click', async () => {
    if (!window.confirm('이 PC의 서버 이력과 연결키를 삭제합니다. 먼저 Agent를 중단해주세요. 로컬 원본은 유지됩니다. 삭제할까요?')) return;
    try {
      await api('connection', { method: 'DELETE' });
      localStorage.removeItem(storageKey); connection = null; showConnection();
      text('connectionStatus', '연결 해제'); text('monitorMessage', '서버 이력과 연결키를 삭제했습니다.');
    } catch (error) { text('monitorMessage', error.message); }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  (async () => {
    try {
      connection = JSON.parse(localStorage.getItem(storageKey) || 'null'); showConnection();
      const status = await api('status'); ready = status.enabled;
      el('pairButton').disabled = !ready;
      text('connectionStatus', ready ? '연결 준비 완료' : '서버 설정 필요');
      text('monitorMessage', ready ? '본인 PC의 연결 설정을 저장하고 Agent를 실행하면 실측값이 표시됩니다. 조회키 백업 파일은 다른 사람에게 공유하지 마세요.' : '모니터링 DB 연결이 아직 완료되지 않았습니다. 서버의 MONITORING_ENABLED와 MONITORING_DATABASE_URL 설정이 필요합니다.');
      if (connection && ready) await refresh();
      timer = setInterval(() => { if (!document.hidden && ready) refresh(); }, 10000);
    } catch (error) { text('monitorMessage', error.message); }
  })();
  window.addEventListener('pagehide', () => clearInterval(timer));
  window.addEventListener('resize', () => drawChart(chartHistory));
})();
