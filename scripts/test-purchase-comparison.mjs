import assert from 'node:assert/strict';
import {test} from 'node:test';
import {candidateCosts, currentParts, retainedParts, benefits} from '../app/purchase-comparison.ts';

const now = Date.parse('2026-09-28T12:00:00Z');
const candidate = {parts:[{key:'ssd',category:'storage',reason:'Replace storage only'}],checks:[{label:'Capacity',status:'passed',detail:'2TB specification'}, {label:'Slot',status:'conditional',detail:'Verify fit'}]};
const quote = changes => ({id:'offer',product_id:'ssd',currency:'USD',amount:'100.10',shipping:'10.20',total:'110.30',availability:'in_stock',observed_at:new Date(now).toISOString(),...changes});

test('shipping-included totals use cents and choose lowest matching offer', () => {
  const totals = candidateCosts(candidate, [quote(), quote({id:'lower',amount:'90.10',total:'100.30'})], now);
  assert.equal(totals[0].cents,10030);
  assert.equal(totals[0].offers[0].id,'lower');
});

test('unknown shipping, stock, wrong product, invalid amounts and stale quotes are excluded', () => {
  for (const changes of [{shipping:null,total:null},{availability:'unknown'},{product_id:'wrong'},
    {amount:'NaN'},{shipping:'-1'},{amount:'0'}, {total:'999'},
    {observed_at:new Date(now-600001).toISOString()}, {observed_at:'invalid'}]) {
    assert.deepEqual(candidateCosts(candidate,[quote(changes)],now),[]);
  }
});

test('every part requires a quote in the same currency', () => {
  const bundle = {...candidate,parts:[...candidate.parts,{key:'memory',category:'memory'}]};
  assert.deepEqual(candidateCosts(bundle,[quote()],now),[]);
  assert.deepEqual(candidateCosts(bundle,[quote(),quote({product_id:'memory',currency:'EUR'})],now),[]);
  assert.equal(candidateCosts(bundle,[quote(),quote({product_id:'memory'})],now)[0].cents,22060);
});

test('native currencies remain separate; no assumed conversion', () => {
  const totals = candidateCosts(candidate,[quote(),quote({currency:'EUR'})],now);
  assert.deepEqual(totals.map(t => t.currency),['EUR','USD']);
});

test('no parts or no quotes does not fabricate a zero-cost estimate', () => {
  assert.deepEqual(candidateCosts(candidate,[],now),[]);
  assert.deepEqual(candidateCosts({...candidate,parts:[]},[quote()],now),[]);
});

test('current and retained parts follow actual collected inventory and replacement categories', () => {
  const diagnosis={inventory:[{kind:'Storage',name:'actual SSD'},{kind:'CPU',name:'actual CPU'},{kind:'Memory',name:'actual RAM'}]};
  assert.deepEqual(currentParts(diagnosis,candidate).map(p=>p.name),['actual SSD']);
  assert.deepEqual(retainedParts(diagnosis,candidate).map(p=>p.name),['actual CPU','actual RAM']);
  assert.deepEqual(currentParts({inventory:[]},candidate),[]);
});

test('benefits use candidate reasons and confirmed checks, not conditional checks or invented scores', () => {
  assert.deepEqual(benefits(candidate),['Replace storage only','2TB specification']);
});
