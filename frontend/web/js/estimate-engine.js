/* Manufacturer specifications are factual; demo prices and workload targets are
   explicit inputs, not measured benchmark results or live market quotations. */
(function (root) {
  'use strict';
  const nv = (series) => `https://www.nvidia.com/en-us/geforce/graphics-cards/${series}/`;
  const amdCpu = (series, model) => `https://www.amd.com/en/products/processors/desktops/ryzen/${series}-series/amd-ryzen-${model}.html`;
  const catalog = [
    { id:'7500f', key:'cpu', name:'Ryzen 5 7500F', socket:'AM5', ram:'DDR5', cores:6, threads:12, year:2023, demo:168000, source:amdCpu(7000,'5-7500f') },
    { id:'9600x', key:'cpu', name:'Ryzen 5 9600X', socket:'AM5', ram:'DDR5', cores:6, threads:12, year:2024, demo:260000, source:amdCpu(9000,'5-9600x') },
    { id:'9700x', key:'cpu', name:'Ryzen 7 9700X', socket:'AM5', ram:'DDR5', cores:8, threads:16, year:2024, demo:360000, source:amdCpu(9000,'7-9700x') },
    { id:'rtx4060', key:'gpu', name:'RTX 4060 8GB', vram:8, psu:550, vendor:'NVIDIA', year:2023, demo:300000, candidate:false, source:nv('40-series/rtx-4060-4060ti') },
    { id:'rtx5060', key:'gpu', name:'RTX 5060 8GB', vram:8, psu:550, vendor:'NVIDIA', year:2025, demo:380000, source:nv('50-series/rtx-5060-family') },
    { id:'rtx5060ti8', key:'gpu', name:'RTX 5060 Ti 8GB', vram:8, psu:600, vendor:'NVIDIA', year:2025, demo:470000, source:nv('50-series/rtx-5060-family') },
    { id:'rtx5060ti16', key:'gpu', name:'RTX 5060 Ti 16GB', vram:16, psu:600, vendor:'NVIDIA', year:2025, demo:550000, source:nv('50-series/rtx-5060-family') },
    { id:'rtx5070', key:'gpu', name:'RTX 5070 12GB', vram:12, psu:650, vendor:'NVIDIA', year:2025, demo:780000, source:nv('50-series/rtx-5070-family') },
    { id:'rx9060xt16', key:'gpu', name:'RX 9060 XT 16GB', vram:16, psu:450, vendor:'AMD', year:2025, demo:450000, source:'https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9060xt.html' }
  ];
  const num = x => Number.isFinite(Number(x)) && Number(x) >= 0 ? Number(x) : 0;
  function identify(name, key) {
    const s = String(name || '').toLowerCase().replace(/\s+/g,'');
    if (/laptop|mobile|노트북/.test(s)) return null;
    if (key === 'cpu') return catalog.find(x => x.key === key && new RegExp(`\\b${x.id}\\b`, 'i').test(String(name))) || null;
    if (key !== 'gpu') return null;
    const match = s.match(/(rtx|rx)(\d{4})(ti|xt)?(super)?/);
    if (!match || match[4]) return null;
    const prefix = match[1] + match[2] + (match[3] || '');
    const memory = s.match(/(\d+)gb/);
    const options = catalog.filter(x => x.key === 'gpu' && x.id.replace(/(ti|xt)(8|16)$/, '$1') === prefix);
    return options.find(x => memory ? x.vram === Number(memory[1]) : options.length === 1) || null;
  }
  function ramInfo(name) {
    const s = String(name || '').toUpperCase();
    const capacity = s.match(/(\d+)\s*GB/);
    const sticks = s.match(/(?:X|\*)\s*(\d+)/);
    return { type:s.match(/DDR[345]/)?.[0] || null, gb:capacity ? Number(capacity[1]) * (sticks ? Number(sticks[1]) : 1) : null };
  }
  function boardInfo(name) {
    const s = String(name || '').toUpperCase();
    if (/\b(?:A620|B650|X670|B840|B850|X870)/.test(s)) return { socket:'AM5', ram:'DDR5' };
    if (/\b(?:A320|A520|B350|B450|B550|X370|X470|X570)/.test(s)) return { socket:'AM4', ram:'DDR4' };
    if (/\b(?:H610|B660|B760|H670|H770|Z690|Z790)/.test(s)) return { socket:'LGA1700', ram:/DDR4|D4/.test(s) ? 'DDR4' : /DDR5|D5/.test(s) ? 'DDR5' : null };
    return { socket:null, ram:null };
  }
  function requirements(purpose, resolution='FHD', cuda=false) {
    return { ram:purpose === '사무' ? 16 : 32,
      vram:purpose === 'AI 작업' ? 16 : purpose === '영상편집' ? 12 : purpose === '게임' ? (resolution === 'FHD' ? 8 : resolution === 'QHD' ? 12 : 16) : 0,
      cores:['영상편집','개발'].includes(purpose) ? 8 : 6, cuda:cuda || purpose === 'AI 작업' };
  }
  function inspect(estimate) {
    const parts = estimate.parts || [];
    const get = key => parts.find(p => p.key === key) || { name:estimate[key] || '', userPrice:0 };
    const cpu = identify(get('cpu').name,'cpu'), gpu = identify(get('gpu').name,'gpu');
    const ram = ramInfo(get('ram').name), board = boardInfo(get('motherboard').name);
    const watts = Number(String(get('power').name).match(/(\d{3,4})\s*[wW]/)?.[1]) || null;
    const checks = [];
    const add = (status,message) => checks.push({status,message});
    if (cpu && board.socket) add(cpu.socket === board.socket ? 'pass':'error', `CPU ${cpu.socket} / 메인보드 ${board.socket}`);
    else add('unknown','CPU 또는 메인보드의 정확한 모델을 확인해야 소켓을 비교할 수 있습니다.');
    const requiredRam = board.ram || cpu?.ram;
    if (requiredRam && ram.type) add(requiredRam === ram.type ? 'pass':'error', `플랫폼 ${requiredRam} / 입력 메모리 ${ram.type}`);
    else add('unknown','메인보드의 메모리 지원 규격을 확인하세요.');
    if (gpu && watts) add(watts >= gpu.psu ? 'pass':'error', `파워 ${watts}W / GPU 제조사 권장 시스템 전력 ${gpu.psu}W`);
    else add('unknown','GPU 모델과 파워 용량을 확인해야 전원 조건을 비교할 수 있습니다.');
    add('unknown','메인보드 BIOS 지원 목록, 케이스 GPU 길이, 전원 커넥터, CPU 쿨러는 별도 확인이 필요합니다.');
    const req = requirements(estimate.purpose, estimate.resolution, estimate.cuda);
    const needs = [];
    if (ram.gb && ram.gb < req.ram) needs.push(`RAM ${ram.gb}GB → 작업 기준 ${req.ram}GB 검토`);
    if (gpu && gpu.vram < req.vram) needs.push(`VRAM ${gpu.vram}GB → 작업 기준 ${req.vram}GB 검토`);
    if (cpu && cpu.cores < req.cores) needs.push(`CPU ${cpu.cores}코어 → 병렬 작업 기준 ${req.cores}코어 검토`);
    if (gpu && req.cuda && gpu.vendor !== 'NVIDIA') needs.push('CUDA 필수 작업에는 NVIDIA GPU 후보를 확인하세요.');
    return { cpu,gpu,ram,board,watts,checks,needs,req,get };
  }
  function demoPrices(parts, overrides={}) {
    return parts.map(part => {
      const model = identify(part.name,part.key);
      const ram = ramInfo(part.name);
      let price = model?.demo;
      if (part.key === 'ram' && ram.gb && ram.type) price = Math.round(ram.gb * (ram.type === 'DDR5' ? 3200 : 2200) / 1000) * 1000;
      if (part.key === 'storage') { const m = String(part.name).match(/(\d+(?:\.\d+)?)\s*TB/i); if (m && /SSD|NVMe/i.test(part.name)) price = Number(m[1]) * 85000; }
      if (part.key === 'motherboard' && boardInfo(part.name).socket) price = boardInfo(part.name).socket === 'AM5' ? 150000 : 100000;
      if (part.key === 'power') { const w = String(part.name).match(/(\d{3,4})\s*W/i); if(w) price = Math.round(Number(w[1]) * 110 / 1000)*1000; }
      if (model && Object.hasOwn(overrides,model.id)) price = num(overrides[model.id]);
      return { ...part, lowestPrice:price > 0 ? price : null, averagePrice:null, available:price > 0,
        mall:'데모 기준가 · 실제 시세 아님', source:'demo', purchaseLink:'', error:price > 0 ? null : '모델을 식별할 수 없어 데모 기준가도 설정하지 않았습니다.' };
    });
  }
  function recommend(estimate, { budget, prices={} }={}) {
    const state = inspect(estimate);
    const total = (estimate.parts || []).reduce((s,p) => s + num(p.userPrice),0);
    const limit = num(budget ?? estimate.budget ?? total);
    const candidates = [];
    for (const item of catalog.filter(x => x.candidate !== false)) {
      const current = state[item.key];
      if (!current || current.id === item.id) continue;
      const currentPart = state.get(item.key);
      const reasons = [], blocked = [], conditional = [];
      if (item.key === 'cpu') {
        if (item.cores <= current.cores || current.cores >= state.req.cores) continue;
        if (!state.board.socket || state.board.socket !== item.socket) blocked.push('CPU 소켓 불일치 또는 미확인');
        if (state.ram.type !== item.ram) blocked.push(`메모리 ${item.ram} 필요`);
        reasons.push(`병렬 작업용 코어 수 ${current.cores} → ${item.cores}, 스레드 ${current.threads} → ${item.threads}`);
        conditional.push('BIOS CPU 지원 목록·쿨러 확인');
      } else {
        // VRAM/CUDA capability candidates, never an asserted FPS upgrade.
        // A larger memory buffer alone must not send a higher-tier GPU to a
        // lower-tier model. Keep comparison pairs deliberately conservative.
        const comparable = {
          rtx4060:['rtx5060ti16','rtx5070','rx9060xt16'],
          rtx5060:['rtx5060ti16','rtx5070','rx9060xt16'],
          rtx5060ti8:['rtx5060ti16'],
          rx9060xt16:['rtx5060ti16']
        };
        if (!(comparable[current.id] || []).includes(item.id)) continue;
        if (!(item.vram > current.vram && current.vram < state.req.vram) && !(state.req.cuda && current.vendor !== 'NVIDIA' && item.vendor === 'NVIDIA')) continue;
        if (item.vram < current.vram || item.vram < state.req.vram || item.year < current.year) continue;
        if (state.req.cuda && item.vendor !== 'NVIDIA') blocked.push('CUDA 필수 조건 불충족');
        if (!state.watts || state.watts < item.psu) blocked.push(`파워 ${item.psu}W 이상 필요`);
        reasons.push(`VRAM ${current.vram}GB → ${item.vram}GB${state.req.cuda ? ' · CUDA 조건 적용' : ''}`);
        conditional.push('게임별 FPS·렌더링 속도 비교, 케이스 길이·커넥터 확인');
      }
      if (state.checks.some(c => c.status === 'error')) blocked.push('기존 견적의 호환성 오류를 먼저 수정하세요.');
      const price = Object.hasOwn(prices,item.id) ? num(prices[item.id]) : item.demo;
      const afterTotal = total - num(currentPart.userPrice) + price;
      if (!price) blocked.push('후보 가격을 입력하세요.');
      if (afterTotal > limit) blocked.push(`예산 ${Math.round(afterTotal-limit).toLocaleString('ko-KR')}원 초과`);
      candidates.push({ ...item,price,total:afterTotal,delta:price-num(currentPart.userPrice),current:current.name,
        reasons,blocked,conditional,eligible:blocked.length === 0 });
    }
    if (state.ram.gb && state.ram.gb < state.req.ram && state.ram.type && state.board.ram === state.ram.type) {
      const capacity = state.req.ram;
      const name = `${capacity}GB ${state.ram.type} (전체 키트 교체)`;
      const price = Math.round(capacity*(state.ram.type === 'DDR5' ? 3200 : 2200)/1000)*1000;
      const afterTotal = total-num(state.get('ram').userPrice)+price;
      const blocked = [];
      if (afterTotal > limit) blocked.push(`예산 ${Math.round(afterTotal-limit).toLocaleString('ko-KR')}원 초과`);
      if (state.checks.some(c => c.status === 'error')) blocked.push('기존 호환성 오류 수정 필요');
      candidates.push({id:'ram-capacity',key:'ram',name,price,total:afterTotal,delta:price-num(state.get('ram').userPrice),current:state.get('ram').name,
        reasons:[`작업 기준에 맞춰 총 메모리 ${state.ram.gb}GB → ${capacity}GB`],blocked,eligible:blocked.length === 0,
        conditional:['추가 장착 비용이 아닌 전체 키트 교체 가격입니다. 보드 최대 용량·슬롯·QVL 확인이 필요합니다.'],source:state.cpu?.source || ''});
    }
    candidates.sort((a,b) => Number(b.eligible)-Number(a.eligible) || a.total-b.total || a.name.localeCompare(b.name));
    return { total,budget:limit,state,candidates,
      explanation:!state.cpu || !state.gpu ? '등록되지 않은 CPU/GPU는 성능을 추정하지 않습니다. 정확한 모델을 입력하거나 카탈로그를 확장해야 합니다.' : state.needs.length ? '설정한 작업 기준의 부족 항목을 보완하는 후보입니다. 속도 향상을 보장하는 순위가 아닙니다.' : '현재 입력에서 설정한 용량·코어 기준의 부족이 확인되지 않아 교체를 강제하지 않습니다. 더 높은 목표를 설정하거나 실제 작업 측정 후 결정하세요.' };
  }
  root.SpecCheckEngine = {catalog,identify,ramInfo,boardInfo,requirements,inspect,demoPrices,recommend};
})(typeof window === 'undefined' ? globalThis : window);
