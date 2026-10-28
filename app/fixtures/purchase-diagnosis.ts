import type { Diagnosis } from '../types';
import { demoDiagnosis } from './demo-diagnosis';

export const purchaseDiagnosis: Diagnosis = {
  ...demoDiagnosis,
  scanId: 'demo-purchase',
  recommendations: [{
    id: 'preview-storage', findingIds: [], priority: 'normal', category: 'storage',
    title: '저장장치 교체 검토 예시', description: '예시 데이터이며 실제 PC 진단 결과가 아닙니다.',
    searchQuery: 'WD_BLACK SN850X 1TB WDS100T2X0E', searchUrl: 'https://www.ebay.com/',
    aiInsight: { provider: 'template', model: 'preview', status: 'fallback', rationale: '화면 검증용 예시입니다. 가격과 재고는 생성하지 않습니다.', cautions: [] },
    candidates: [{
      id: 'preview-sn850x', strategy: 'minimal', title: 'SSD 단품 교체', summary: '기존 시스템을 유지하는 예시 후보입니다.',
      recommended: true, compatibilityStatus: 'conditional', compatibilityScore: 60,
      checks: [{ label: '슬롯', status: 'conditional', detail: 'M.2 2280 NVMe 슬롯 지원 여부 확인 필요' }],
      parts: [{ key: 'wd-black-sn850x-1tb', category: 'storage', name: 'WD_BLACK SN850X 1TB',
        searchQuery: 'WD_BLACK SN850X 1TB WDS100T2X0E', reason: '기존 예시 디스크와 같은 1TB 용량을 유지하는 단품 교체안',
        specifications: ['NVMe', 'M.2 2280', '1TB'], sourceLabel: null, sourceUrl: null }],
      tradeoffs: ['판매 가격과 한국 배송비 확인 필요'],
    }, {
      id: 'preview-p41', strategy: 'minimal', title: 'SK hynix Platinum P41 2TB',
      summary: '저장장치만 교체하면서 용량을 늘리는 예시 후보입니다.',
      recommended: false, compatibilityStatus: 'conditional', compatibilityScore: 60,
      checks: [{label: '용량', status: 'passed', detail: '기존 예시의 1TB보다 큰 2TB 용량입니다.'},
        {label: '슬롯', status: 'conditional', detail: 'M.2 2280 NVMe 장착 규격과 방열 공간 확인 필요'}],
      parts: [{key: 'sk-hynix-platinum-p41-2tb', category: 'storage', name: 'SK hynix Platinum P41 2TB',
        searchQuery: 'SK hynix Platinum P41 2TB', reason: '용량 증가를 함께 검토하는 2TB 후보',
        specifications: ['NVMe', 'M.2 2280', '2TB'], sourceLabel: 'SK hynix 제품 사양', sourceUrl: 'https://ssd.skhynix.com/kr/platinum_p41/'}],
      tradeoffs: ['저장 용량 증가', '가격·한국 배송비와 데이터 이전 비용은 미확인'],
    }],
  }],
};
