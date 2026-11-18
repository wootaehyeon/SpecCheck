'use client';

import { useEffect, useState } from 'react';
import { diagnosticsConfig } from './config';
import { requestJson } from './diagnostics-request';
import { Button } from '@/components/ui/button';

type Volume = { drive: string; free_percent: number | null; free_gb: number | null; disk_index: number | null; model: string | null };
type Disk = { name: string; Read: number | null; Write: number | null };
type Result = {
  candidates: { signal: string; seconds: number }[];
  rankings: { name: string; value: number }[][];
  timeline: { t: number; cpu: number; memory: number; disks: Disk[]; leaders: (string | null)[] }[];
};
const labels = ['CPU', '메모리', 'I/O'];
const units = ['%', 'MiB', 'MiB/s'];
const field = 'rounded border bg-background px-2 py-1';
const api = diagnosticsConfig.agentUrl + '/api';

function Report({ result, title }: { result: Result; title: string }) {
  return <article className="min-w-0 space-y-3 rounded-lg border p-4">
    <h3 className="font-semibold">{title}</h3>
    {result.candidates.length ? result.candidates.map(({signal, seconds}) =>
      <p key={signal}><strong>{signal}</strong> 부하가 {seconds}초 연속 관측됐습니다. {
        signal === 'CPU' ? 'CPU 상위 앱의 백그라운드 작업을 멈추고 다시 측정해 보세요.' :
        signal === '메모리' ? '사용하지 않는 메모리 상위 앱을 닫고 다시 측정해 보세요.' :
        '파일 복사나 동기화가 진행 중이면 잠시 멈추고 다시 측정해 보세요.'}</p>)
      : <p>측정 구간에서 병목이 확인되지 않음</p>}
    {result.rankings.map((apps, i) => <div key={labels[i]}><strong>{labels[i]} 상위 앱 · 구간 평균</strong>
      <p>{apps.map(app => app.name + ' ' + app.value + units[i]).join(' · ') || '관측값 없음'}</p></div>)}
    <details><summary className="cursor-pointer">시간대별 부하와 물리 디스크 지연</summary>
      <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr>
        {['경과', 'CPU / 메모리', '상위 앱 (CPU / 메모리 / I/O)', '디스크별 읽기 / 쓰기 (ms)'].map(h => <th key={h}>{h}</th>)}
      </tr></thead><tbody>{result.timeline.map(row => <tr key={row.t} className="border-t align-top">
        <td>{row.t}초</td><td>{row.cpu}% / {row.memory}%</td><td>{row.leaders.map(n => n ?? '—').join(' / ')}</td>
        <td>{row.disks.length ? row.disks.map(d => <div key={d.name}>디스크 {d.name} · {d.Read ?? '—'} / {d.Write ?? '—'}</div>) : '관측값 없음'}</td>
      </tr>)}</tbody></table></div><p>— 표시는 해당 구간에 계산 가능한 관측값이 없음을 뜻합니다. 앱 I/O에는 파일 외 입출력도 포함됩니다.</p>
    </details>
  </article>;
}

export function WorkloadPanel({ scanId }: { scanId?: string }) {
  const [volumes, setVolumes] = useState<Volume[]>([]);
  const [volumeError, setVolumeError] = useState('');
  const [task, setTask] = useState('');
  const [action, setAction] = useState('');
  const [runs, setRuns] = useState<Result[]>([]);
  const [times, setTimes] = useState(['', '']);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    if (scanId) requestJson<Volume[]>(api + '/scans/' + encodeURIComponent(scanId) + '/volumes', undefined, 10000)
      .then(v => { if (active) setVolumes(v); })
      .catch(e => { if (active) setVolumeError(e.message); });
    return () => { active = false; };
  }, [scanId]);

  async function record() {
    setBusy(true);
    setError('');
    try {
      const result = await requestJson<Result>(api + '/workload', { method: 'POST' }, 85000);
      setRuns(previous => [...previous, result]);
    } catch (e) { setError(e instanceof Error ? e.message : '측정에 실패했습니다.'); }
    finally { setBusy(false); }
  }
  return <section className="mb-6 space-y-4 rounded-xl border p-5 text-sm">
    <h2 className="text-lg font-semibold">드라이브별 공간</h2>
    {volumes.length ? volumes.map(v => <div key={v.drive}><strong>{v.drive}</strong> {v.free_percent != null && Math.round(100 - v.free_percent) + '% 사용'} · {v.free_gb ?? '—'} GB 여유 · {v.disk_index == null ? '물리 디스크 연결 미확인' : '디스크 ' + v.disk_index + ' ' + (v.model ?? '')}</div>)
      : <p>{volumeError || '표시할 볼륨 정보가 없습니다.'}</p>}
    {Array.from(new Set(volumes.map(v => v.disk_index))).filter(index => index != null).map(index => {
      const shared = volumes.filter(v => v.disk_index === index);
      return shared.length > 1 && <p key={index}>{shared.map(v => v.drive).join(', ')}는 같은 디스크 {index}에 있습니다.</p>;
    })}
    <h2 className="text-lg font-semibold">증상 재현 진단</h2>
    <p>측정을 시작하면 같은 PC에서 느린 작업을 실행하세요. 약 30초 동안 기록합니다.</p>
    <div className="flex flex-wrap items-center gap-3">
      <label>앱과 작업 <input className={field} disabled={busy || !!runs.length} value={task} placeholder="예: 게임에서 저장 파일 불러오기" onChange={e => setTask(e.target.value)} /></label>
      {!!runs.length && <label>적용한 조치 <input className={field} disabled={busy || runs.length > 1} value={action} onChange={e => setAction(e.target.value)} /></label>}
      {runs.length < 2 && <Button onClick={record} disabled={busy || !task.trim() || (!!runs.length && !action.trim())}>{busy ? '측정 중…' : runs.length ? '같은 작업 다시 측정' : '30초 측정 시작'}</Button>}
      {!!runs.length && !busy && <Button variant="outline" onClick={() => { setRuns([]); setTimes(['', '']); setAction(''); setError(''); }}>새 비교 시작</Button>}
    </div>
    {error && <p role="alert">{error}</p>}
    <div className="grid gap-4 lg:grid-cols-2">{runs.map((r, i) => <div key={i} className="space-y-2">
      <Report result={r} title={i ? action + ' 후 · ' + task : '조치 전 · ' + task} />
      <label>실제 작업 소요 시간(초) <input type="number" min="0.1" step="any" className={field + ' w-24'} value={times[i]} onChange={e => setTimes(times.map((v, j) => i === j ? e.target.value : v))} /></label>
    </div>)}</div>
    {runs.length === 2 && times.every(v => Number(v) > 0) && <p><strong>{task} · {times[0]}초 → {times[1]}초</strong> ({action} 후). {Number(times[1]) < Number(times[0]) ? '이번 측정에서 작업 시간이 줄었습니다.' : '이번 측정에서 작업 시간 단축이 확인되지 않았습니다.'}</p>}
  </section>;
}
