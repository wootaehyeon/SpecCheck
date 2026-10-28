'use strict';
(() => {
  const key = 'speccheck.purchase.context.v1';
  const storageRules = ['HW-DISK-001', 'RL-DISK-001', 'ST-SMART-001', 'ST-SMART-002', 'ST-WEAR-001'];
  const memoryRules = ['HW-RAM-002', 'PF-MEM-001', 'RL-WHEA-001'];
  const profile = (rule) => storageRules.includes(rule)
    ? { category: 'storage', label: 'SSD 구매하기', query: 'NVMe SSD 1TB' }
    : memoryRules.includes(rule)
      ? { category: 'memory', label: '메모리 구매하기', query: '메모리 16GB' }
      : { category: 'other', label: '교체 부품 찾아보기', query: '' };

  function remember(finding, hardware) {
    // 조회키, 기기 ID, 프로세스 등은 구매 화면이나 판매처에 전달하지 않는다.
    const context = {
      rule: finding.rule_id, title: finding.title, summary: finding.summary,
      detail: finding.action_detail, savedAt: Date.now(),
      board: hardware.motherboard?.product || '',
      memory: hardware.memory?.total_gb,
      disks: (hardware.storage || []).map((disk) => disk.model).filter(Boolean).join(', '),
    };
    try { sessionStorage.setItem(key, JSON.stringify(context)); } catch { /* URL의 규칙으로 계속 진행 */ }
  }

  function read(rule) {
    try {
      const context = JSON.parse(sessionStorage.getItem(key) || 'null');
      return context?.rule === rule && Date.now() - context.savedAt < 60 * 60 * 1000 ? context : null;
    } catch { return null; }
  }

  window.SpecCheckPurchase = { profile, remember, read };
})();
