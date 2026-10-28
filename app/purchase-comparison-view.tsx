'use client';

import { useState } from 'react';
import { ArrowRight, CircleDollarSign, ExternalLink, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Diagnosis } from './types';
import { benefits, candidateCosts, currentParts, money, retainedParts } from './purchase-comparison';
import type { PurchaseQuote } from './purchase-comparison';

export function PurchaseComparison({ diagnosis, offers }: { diagnosis: Diagnosis; offers: PurchaseQuote[] }) {
  const [mode, setMode] = useState<'cost' | 'benefits'>('cost');
  return <div className="min-w-0 space-y-4">
    <div className="inline-flex flex-wrap gap-1 rounded-md border border-white/10 p-1" role="group" aria-label="견적 비교 보기">
      <Button size="sm" variant={mode === 'cost' ? 'secondary' : 'ghost'} aria-pressed={mode === 'cost'} onClick={() => setMode('cost')}><CircleDollarSign className="size-4" />비용 비교</Button>
      <Button size="sm" variant={mode === 'benefits' ? 'secondary' : 'ghost'} aria-pressed={mode === 'benefits'} onClick={() => setMode('benefits')}><TrendingUp className="size-4" />교체 효과</Button>
    </div>
    {diagnosis.recommendations.map(recommendation => {
      const rows = recommendation.candidates.map(candidate => ({ candidate, costs: candidateCosts(candidate, offers) }));
      const baseline = rows.find(row => row.candidate.recommended);
      return <section key={recommendation.id} className="space-y-3">
        <h4 className="text-xs font-semibold">{recommendation.title}</h4>
        <p className="text-xs leading-5 text-muted-foreground">{recommendation.description}</p>
        <div className="w-full min-w-0 max-w-full overflow-x-auto rounded-md border border-white/10">
          <table className="w-full min-w-[700px] table-fixed text-left text-xs">
            <thead className="border-b border-white/10 bg-white/[.03] text-muted-foreground"><tr>
              <th className="w-[28%] p-3 font-medium">교체안</th>
              <th className="w-[24%] p-3 font-medium">{mode === 'cost' ? '배송 포함 부품 합계' : '기대 효과·근거'}</th>
              <th className="w-[23%] p-3 font-medium">{mode === 'cost' ? '권장안 대비 차액' : '교체 목록 외 기존 부품'}</th>
              <th className="w-[25%] p-3 font-medium">{mode === 'cost' ? '상품 확인' : '구매 전 주의사항'}</th>
            </tr></thead>
            <tbody>{rows.map(({ candidate, costs }) => <tr key={candidate.id} className={`border-b border-white/10 align-top last:border-b-0 ${candidate.recommended ? 'bg-primary/[.04]' : ''}`}>
              <td className="space-y-2 p-3"><div className="font-medium">{candidate.title}{candidate.recommended && <span className="ml-2 text-primary">권장</span>}</div>
                <div className="break-words text-muted-foreground">{currentParts(diagnosis, candidate).map(p => p.name).join(' · ') || '현재 부품 미확인'}</div>
                {currentParts(diagnosis, candidate).length > 1 && <p className="text-[11px] text-amber-300">여러 장치 수집됨 · 교체 대상 별도 확인</p>}
                <ArrowRight className="size-3 text-muted-foreground" aria-label="교체 후" />
                <div className="break-words">{candidate.parts.map(p => p.name).join(' + ')}</div>
                <div className={candidate.compatibilityStatus === 'passed' ? 'text-emerald-300' : 'text-amber-300'}>{candidate.compatibilityStatus === 'passed' ? '확인 조건 일치' : '장착 조건 추가 확인'}</div>
              </td>
              {mode === 'cost' ? <>
                <td className="space-y-2 p-3">{costs.length ? costs.map(cost => <div key={cost.currency} className="font-semibold">{money(cost.cents, cost.currency)}</div>) : <span className="text-muted-foreground">미확인</span>}
                  <p className="text-[11px] leading-4 text-muted-foreground">관세·부가세·작업 비용 제외</p>
                </td>
                <td className="space-y-2 p-3">{costs.length ? costs.map(cost => {
                  const reference = baseline?.costs.find(value => value.currency === cost.currency);
                  if (!reference) return <div key={cost.currency} className="text-muted-foreground">{cost.currency} 비교 불가</div>;
                  const delta = cost.cents - reference.cents;
                  return <div key={cost.currency} className={delta < 0 ? 'text-emerald-300' : 'text-muted-foreground'}>{delta === 0 ? '동일 금액' : `${delta < 0 ? '-' : '+'}${money(Math.abs(delta), cost.currency)}`}</div>;
                }) : <span className="text-muted-foreground">비교 불가</span>}</td>
                <td className="space-y-2 p-3">{costs.flatMap(cost => cost.offers).filter((offer, index, all) => all.findIndex(o => o.id === offer.id) === index).map(offer => <a key={offer.id} href={offer.url} target="_blank" rel="noreferrer" className="flex items-start gap-1 break-words text-primary">{offer.title}<ExternalLink className="size-3 shrink-0" /></a>)}
                  {candidate.parts.map(part => <a key={part.key} href={`https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(part.searchQuery)}`} target="_blank" rel="noreferrer" className="flex items-start gap-1 break-words text-primary">{part.name} 검색<ExternalLink className="size-3 shrink-0" /></a>)}
                </td>
              </> : <>
                <td className="space-y-2 p-3 leading-5">{benefits(candidate).map(value => <p key={value}>{value}</p>)}<p className="text-[11px] text-muted-foreground">실사용 속도·성능 향상률은 미측정</p></td>
                <td className="space-y-2 p-3 text-muted-foreground">{retainedParts(diagnosis, candidate).map(part => <p key={`${part.kind}-${part.name}`} className="break-words">{part.name}</p>)}{retainedParts(diagnosis, candidate).length === 0 && '수집 정보 없음'}</td>
                <td className="space-y-2 p-3 leading-5 text-amber-300">{candidate.checks.filter(check => check.status !== 'passed').map(check => <p key={check.label}>{check.detail}</p>)}{candidate.checks.every(check => check.status === 'passed') && '장착 환경과 판매 조건 최종 확인'}
                  {candidate.parts.filter(part => part.sourceUrl).map(part => <a key={part.key} href={part.sourceUrl!} target="_blank" rel="noreferrer" className="flex items-start gap-1 text-primary">{part.sourceLabel || '제조사 사양'}<ExternalLink className="size-3 shrink-0" /></a>)}
                </td>
              </>}
            </tr>)}</tbody>
          </table>
        </div>
      </section>;
    })}
  </div>;
}
