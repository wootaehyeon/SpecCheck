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
        searchQuery: 'WD_BLACK SN850X 1TB WDS100T2X0E', reason: '화면 검증용 교체 후보',
        specifications: ['NVMe', 'M.2 2280', '1TB'], sourceLabel: null, sourceUrl: null }],
      tradeoffs: ['판매 가격과 한국 배송비 확인 필요'],
    }],
  }],
};
