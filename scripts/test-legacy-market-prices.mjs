import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
const engineSource=readFileSync(new URL('../frontend/web/js/estimate-engine.js',import.meta.url),'utf8');
const script=readFileSync(new URL('../frontend/web/js/script.js',import.meta.url),'utf8');
function setup() {
  const store=new Map();
  const c=vm.createContext({window:{location:{hostname:'localhost',port:'8087',protocol:'http:'},addEventListener(){},matchMedia:()=>({matches:true})},localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},console,URL,AbortController,setTimeout,clearTimeout});
  vm.runInContext(engineSource,c);vm.runInContext(script,c);
  return {e:c.window.SpecCheckEngine,c};
}
const fixturePrices={rx9060xt16:450000,rtx5060ti16:550000,rtx5070:780000,'9700x':360000,'ram-capacity':102000};
const base=()=>({purpose:'게임',resolution:'QHD',parts:[{key:'cpu',name:'Ryzen 5 7500F',userPrice:180000},{key:'gpu',name:'RTX 4060',userPrice:430000},{key:'ram',name:'32GB DDR5',userPrice:110000},{key:'storage',name:'1TB NVMe SSD',userPrice:95000},{key:'motherboard',name:'B650M',userPrice:160000},{key:'power',name:'600W',userPrice:65000}]});
test('exact models, memory variants and unknown models remain distinct',()=>{
  const {e}=setup();
  assert.equal(e.identify('AMD Ryzen 5 7500F','cpu').socket,'AM5');
  assert.equal(e.identify('RTX 4060 Ti','gpu'),null);
  assert.equal(e.identify('RTX 5060 Ti','gpu'),null);
  assert.equal(e.identify('RTX 5060 Ti 16GB','gpu').vram,16);
  assert.equal(e.identify('RTX 5060 Laptop','gpu'),null);
  assert.equal(e.identify('RTX 5090','gpu'),null);
});
test('QHD candidates meet memory goal and never recommend the same 4060',()=>{
  const {e}=setup();const r=e.recommend(base(),{budget:1200000,prices:fixturePrices});
  assert.ok(r.candidates.some(c=>c.id==='rx9060xt16'&&c.eligible));
  assert.ok(r.candidates.every(c=>c.id!=='rtx4060'&&c.vram>=12));
});
test('candidate total replaces original cost rather than adding both',()=>{
  const {e}=setup();const r=e.recommend(base(),{budget:1200000,prices:fixturePrices});const x=r.candidates.find(c=>c.id==='rx9060xt16');
  assert.equal(r.total,1040000);assert.equal(x.total,1060000);assert.equal(x.delta,20000);
});
test('budget excess and insufficient power block application',()=>{
  const {e}=setup();const r=e.recommend(base(),{budget:1040000,prices:fixturePrices});assert.ok(r.candidates.every(c=>!c.eligible));
  const x=e.recommend(base(),{budget:2000000,prices:fixturePrices}).candidates.find(c=>c.id==='rtx5070');assert.ok(x.blocked.some(s=>s.includes('650W')));
});
test('changing candidate prices changes budget eligibility',()=>{
  const {e}=setup();const x=e.recommend(base(),{budget:1040000,prices:{rx9060xt16:400000}}).candidates.find(c=>c.id==='rx9060xt16');
  assert.equal(x.total,1010000);assert.equal(x.eligible,true);
});
test('CUDA requirement excludes AMD candidates',()=>{
  const {e}=setup();const b=base();b.purpose='AI 작업';const r=e.recommend(b,{budget:1400000,prices:fixturePrices});
  assert.ok(r.candidates.filter(x=>x.eligible).every(x=>x.vendor==='NVIDIA'));
  assert.ok(r.candidates.some(x=>x.id==='rtx5060ti16'&&x.eligible));
});
test('AM4 motherboard cannot accept AM5 CPU and all changes block until repaired',()=>{
  const {e}=setup();const b=base();b.parts.find(x=>x.key==='motherboard').name='B550M';
  assert.ok(e.inspect(b).checks.some(x=>x.status==='error'));
  assert.ok(e.recommend(b,{budget:2000000,prices:fixturePrices}).candidates.every(x=>!x.eligible));
});
test('DDR4 on AM5 is rejected',()=>{const {e}=setup();const b=base();b.parts.find(x=>x.key==='ram').name='32GB DDR4';assert.ok(e.inspect(b).checks.some(x=>x.status==='error'&&x.message.includes('DDR4')));});
test('FHD baseline is not forced into buying a replacement',()=>{const {e}=setup();const b=base();b.resolution='FHD';assert.equal(e.recommend(b,{budget:2000000,prices:fixturePrices}).candidates.length,0);});
test('parallel workload yields same-socket higher-core CPU candidate',()=>{const {e}=setup();const b=base();b.purpose='개발';const r=e.recommend(b,{budget:1400000,prices:fixturePrices});assert.ok(r.candidates.some(x=>x.id==='9700x'&&x.eligible));});
test('unknown high-end GPU never silently downgraded to a known model',()=>{const {e}=setup();const b=base();b.parts.find(x=>x.key==='gpu').name='RTX 5090';assert.ok(e.recommend(b,{budget:5000000}).candidates.every(x=>x.key!=='gpu'));});
test('5070 is not downgraded to 5060 Ti merely for a larger VRAM number',()=>{const {e}=setup();const b=base();b.resolution='UHD';b.parts.find(x=>x.key==='gpu').name='RTX 5070';b.parts.find(x=>x.key==='power').name='750W';assert.ok(e.recommend(b,{budget:5000000}).candidates.every(x=>x.key!=='gpu'));});
test('no candidate has an automatic example price',()=>{const {e}=setup(); const r=e.recommend(base(),{budget:2000000});assert.ok(r.candidates.length);assert.ok(r.candidates.every(x=>!x.eligible && x.price===0));assert.ok(e.catalog.every(x=>x.demo===undefined));});
test('analysis computes mismatch and never invents risk scores or benchmarks',()=>{
  const {c}=setup();const b=base();b.parts.find(x=>x.key==='power').name='300W';const r=c.analyzeEstimate(b,c.normalizeMarketPrices(b.parts,[]));
  assert.equal(r.purchaseStatus,'호환성 수정 필요');assert.equal(r.riskScore,null);assert.equal(r.detail.balance.score,undefined);assert.equal(r.priceCompare.averageTotal,null);
});
test('RAM kit capacities are counted and capacity candidate includes replacement cost',()=>{
  const {e}=setup();assert.equal(e.ramInfo('16GB x2 DDR5').gb,32);const b=base();b.parts.find(x=>x.key==='ram').name='16GB DDR5';
  const r=e.recommend(b,{budget:1300000,prices:fixturePrices});assert.ok(r.candidates.some(x=>x.key==='ram'&&x.eligible));
});

test('eBay foreign prices remain informational and never become a won overpay comparison',()=>{
  const {c}=setup();
  const parts=[{key:'storage',name:'Fixture SSD 1TB',userPrice:99000}];
  const normalized=c.normalizeMarketPrices(parts,[{key:'storage',lowestPrice:0,averagePrice:0,errorCode:'currency_mismatch',error:'native currency only',source:'ebay_browse',nativePrices:[{currency:'USD',lowest:'99.95'}],purchaseLink:'https://www.ebay.com/itm/123456789012'}]);
  assert.equal(normalized[0].available,false);
  assert.equal(normalized[0].lowestPrice,null);
  assert.equal(normalized[0].nativePrices[0].currency,'USD');
  assert.equal(c.makePriceComparison(normalized[0]).diff,null);
});


test('lowest price remains usable without an average; demo source stays unavailable',()=>{
 const {c}=setup();const parts=base().parts;
 const rows=c.normalizeMarketPrices(parts,[{key:'cpu',lowestPrice:170000,source:'ebay_browse'},{key:'gpu',lowestPrice:1,averagePrice:1,source:'demo'}]);
 assert.equal(rows[0].available,true);assert.equal(rows[0].averagePrice,null);assert.equal(rows[1].available,false);
});
test('render keeps actual API prices instead of replacing them with examples',()=>{
 const {c}=setup();const b=base();const result=c.analyzeEstimate(b,c.normalizeMarketPrices(b.parts,b.parts.map(p=>({...p,lowestPrice:123456,source:'ebay_browse'}))));
 c.saveData('estimateInput',b); c.document={getElementById:()=>null};c.renderResult(result);
 assert.equal(result.priceCompare.parts[0].lowestPrice,123456);
});
