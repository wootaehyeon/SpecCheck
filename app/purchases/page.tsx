'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { diagnosticsConfig } from '../config';
import { mountPurchaseHistory } from '../../frontend/web/js/purchase-history.js';
import '../../frontend/web/css/purchase-history.css';

export default function PurchasesPage() {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (container.current) return mountPurchaseHistory(container.current, { apiBase: diagnosticsConfig.agentUrl });
  }, []);
  return <main className="mx-auto max-w-6xl px-4 py-8">
    <Link href="/" className="mb-6 inline-block text-sm text-primary">← PC 진단으로</Link>
    <div ref={container} />
    <noscript>구매이력을 조회하려면 JavaScript를 활성화하세요.</noscript>
  </main>;
}
