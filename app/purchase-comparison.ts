import type { Diagnosis } from './types';

export type Candidate = Diagnosis['recommendations'][number]['candidates'][number];
export type PurchaseQuote = {
  id: string; product_id: string; title: string; url: string; amount: string;
  currency: string; shipping: string | null; total: string | null;
  availability: 'in_stock' | 'unknown'; observed_at: string;
};
export type CandidateCost = { currency: string; cents: number; offers: PurchaseQuote[] };

function cents(value: string | null) {
  if (value === null || value.trim() === '') return null;
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0 || amount > 100000000) return null;
  return Math.round(amount * 100);
}

export function candidateCosts(candidate: Candidate, offers: PurchaseQuote[], now = Date.now()): CandidateCost[] {
  if (!candidate.parts.length) return [];
  const byPart = candidate.parts.map(part => {
    const currencies = new Map<string, { cents: number; offer: PurchaseQuote }>();
    for (const offer of offers.filter(o => o.product_id === part.key)) {
      const item = cents(offer.amount), shipping = cents(offer.shipping), total = cents(offer.total);
      const observed = Date.parse(offer.observed_at);
      if (offer.availability !== 'in_stock' || item === null || item <= 0 || shipping === null || total === null
        || item + shipping !== total || !Number.isFinite(observed) || now - observed > 600000 || observed > now + 300000) continue;
      const previous = currencies.get(offer.currency);
      if (!previous || total < previous.cents) currencies.set(offer.currency, { cents: total, offer });
    }
    return currencies;
  });
  return [...byPart[0].keys()].filter(currency => byPart.every(part => part.has(currency))).map(currency => ({
    currency, cents: byPart.reduce((sum, part) => sum + part.get(currency)!.cents, 0),
    offers: byPart.map(part => part.get(currency)!.offer),
  })).sort((a, b) => a.currency.localeCompare(b.currency));
}

export function currentParts(diagnosis: Diagnosis, candidate: Candidate) {
  const categories = new Set(candidate.parts.map(part => part.category));
  return diagnosis.inventory.filter(item => categories.has(item.kind.toLowerCase() as Candidate['parts'][number]['category']));
}

export function retainedParts(diagnosis: Diagnosis, candidate: Candidate) {
  const categories = new Set(candidate.parts.map(part => part.category));
  return diagnosis.inventory.filter(item => !categories.has(item.kind.toLowerCase() as Candidate['parts'][number]['category']));
}

export function benefits(candidate: Candidate) {
  return [...new Set([
    ...candidate.parts.map(part => part.reason),
    ...candidate.checks.filter(check => check.status === 'passed' && !check.label.includes('출처')).map(check => check.detail),
  ])].slice(0, 4);
}

export function money(cents: number, currency: string) {
  return new Intl.NumberFormat('ko-KR', { style: 'currency', currency }).format(cents / 100);
}
