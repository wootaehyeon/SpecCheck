'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { requestJson } from './diagnostics-request';
import { diagnosticsConfig } from './config';
import type { Diagnosis } from './types';

type Offer = {
  id: string; product_id: string; title: string; url: string; amount: string;
  currency: string; shipping: string | null; total: string | null;
  availability: 'in_stock' | 'unknown'; observed_at: string;
};
type State = { mode: string; offers: Offer[]; best: Offer[]; products: Array<{product_id: string; message: string}> };
const money = (amount: string, currency: string) => new Intl.NumberFormat('ko-KR', { style: 'currency', currency }).format(Number(amount));

export function PurchaseOffers({ diagnosis, onUpdated }: { diagnosis: Diagnosis; onUpdated: () => Promise<void> }) {
  const parts = [...new Map(diagnosis.recommendations.flatMap(r => r.candidates.flatMap(c => c.parts)).map(p => [p.key, p])).values()];
  const productIds = parts.map(p => p.key).sort().join(',');
  const recommendedIds = new Set(diagnosis.recommendations.flatMap(r => r.candidates.filter(c => c.recommended).flatMap(c => c.parts.map(p => p.key))));
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setState(null); setError('');
    const query = new URLSearchParams();
    productIds.split(',').filter(Boolean).forEach(id => query.append('product_id', id));
    const read = () => requestJson<State>(`${diagnosticsConfig.agentUrl}/api/purchase/quotes?${query}`, undefined, 25000)
      .then(data => { if (active) setState(data); })
      .catch(cause => { if (active) { setState(null); setError(cause instanceof Error ? cause.message : '가격 조회 실패'); } });
    void read();
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void read(); }, 300000);
    return () => { active = false; clearInterval(timer); };
  }, [diagnosis.scanId, productIds, revision]);
  async function refresh() {
    setBusy(true); setError('');
    try { await onUpdated(); }
    catch { setError('추천을 갱신하지 못했습니다. 기존 기술적 추천을 유지합니다.'); }
    finally { setRevision(value => value + 1); setBusy(false); }
  }
  return <section className="space-y-4 border-t border-white/10 pt-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-sm font-semibold">구매 가격 비교</h3>
      <Button size="sm" variant="outline" disabled={busy || diagnosis.scanId === 'demo-purchase'} onClick={() => void refresh()}><RefreshCw className={`size-4 ${busy ? 'animate-spin' : ''}`} />{busy ? '갱신 중' : '추천 갱신'}</Button>
    </div>
    {error && <p role="alert" className="text-xs text-amber-300">가격 미확인 · {error}</p>}
    {!state && !error && <p className="text-xs text-muted-foreground">후보 판매 정보 확인 중</p>}
    {parts.filter(part => recommendedIds.has(part.key) || state?.offers.some(o => o.product_id === part.key)).map(part => {
      const offers = state?.offers.filter(o => o.product_id === part.key) ?? [];
      return <div key={part.key} className="space-y-2 border-b border-white/10 pb-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{part.name}</span>
          <a href={`https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(part.searchQuery)}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary">eBay 검색<ExternalLink className="size-3" /></a>
        </div>
        {offers.length === 0 && state && <p className="text-muted-foreground">{state.products.find(p => p.product_id === part.key)?.message ?? '가격 미확인'}</p>}
        {offers.map(offer => <div key={offer.id} className="space-y-1 border-l border-white/10 pl-3">
          <a href={offer.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-words text-primary">{offer.title}<ExternalLink className="size-3 shrink-0" /></a>
          <p>상품 {money(offer.amount, offer.currency)} · 한국 배송 {offer.shipping === null ? '미확인' : money(offer.shipping, offer.currency)} · 합계 {offer.total === null ? '미확인' : money(offer.total, offer.currency)}</p>
          <p className="text-muted-foreground">{offer.availability === 'in_stock' ? '재고 있음 · API 추정' : '재고 미확인'} · 조회 {new Date(offer.observed_at).toLocaleString('ko-KR')}</p>
          {state?.best.some(o => o.id === offer.id) && <p className="text-emerald-300">조회된 동일 부품·동일 통화 상품 중 배송 포함 최저</p>}
        </div>)}
      </div>;
    })}
    {state?.mode === 'technical_only' && <p className="text-xs text-muted-foreground">현재는 사양·호환성 기반 교체 제안입니다. 가격과 재고는 확인되지 않았습니다.</p>}
    <p className="text-[11px] text-muted-foreground">새 상품 · 한국 배송 기준 · 관세·부가세 제외 · 통화별 비교 · 시장 전체 최저가가 아님</p>
  </section>;
}
