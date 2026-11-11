const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static-src/js/clinical.js', 'utf8');
const settle = async () => { for (let n = 0; n < 45; n++) await Promise.resolve(); };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function viewer(total = 120, fail = false, holdImages = false, planes = 1, failures = new Set(), deferMetadata = false, fastTimeout = false, byteSuccess = false) {
  const sets = [], calls = [], images = [], held = [], metaHeld = [], windowEvents = {}, byteCalls = [];
  class Element {
    constructor() { this.events = {}; this.attrs = {}; this.clientHeight = 400; }
    addEventListener(name, callback) { this.events[name] = callback; }
    getAttribute(name) { return this.attrs[name]; }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
    set src(value) { this.attrs.src = value; this.complete = true; this.naturalWidth = 512; this.naturalHeight = 512; }
    get src() { return this.attrs.src; }
  }
  const series = Array.from({length: planes}, (_, plane) => {
    const selectors = Object.fromEntries(['.series-controls', 'input', 'output', '[data-previous]', '[data-next]', '.series-frame', '[data-current-slice]', '[data-series-status]'].map(k => [k, new Element()]));
    selectors['.series-controls'].querySelector = k => selectors[k];
    sets.push(selectors);
    return {dataset: {count: String(total), endpoint: `/synthetic/${plane}/slices/`}, querySelector: k => selectors[k], getAttribute: () => 'Synthetic series'};
  });
  const context = {
    document: {querySelectorAll: () => series}, window: {addEventListener(name, callback) {windowEvents[name] = callback;}}, AbortController, location: {href: "http://synthetic.local"}, URL, Blob, DOMException,
    setTimeout: (fn, ms) => setTimeout(fn, fastTimeout && ms === 8000 ? 15 : ms).unref(), clearTimeout, Date,
    Image: class {
      constructor() { this.naturalWidth = 512; this.naturalHeight = 512; }
      set src(value) { this.url = value; images.push(value); if (failures.has(value)) queueMicrotask(() => this.onerror?.()); else if (holdImages) held.push(() => this.onload?.()); else queueMicrotask(() => this.onload?.()); }
      get src() { return this.url; }
      removeAttribute() { this.url = ""; }
      decode() { return Promise.resolve(); }
    },
    fetch: async url => {
      const u = new URL(url, 'http://synthetic.local');
      const index = Number(u.searchParams.get('index'));
      const before = Number(u.searchParams.get('before'));
      const after = Number(u.searchParams.get('after'));
      const count = Number(u.searchParams.get('count'));
      if (u.pathname.endsWith('.jpg')) { byteCalls.push(u.pathname); return byteSuccess ? byteResponse() : {ok: false}; }
      calls.push(count ? {index, count} : {index, before, after});
      if (deferMetadata && calls.length === 1) return new Promise(resolve => metaHeld.push(resolve));
      if (fail) return {ok: false};
      const start = Math.max(0, index - before), end = Math.min(total, index + (count || after + 1));
      return {ok: true, json: async () => ({index, total, ttl: 300, images: Array.from({length: end - start}, (_, i) => ({index: start + i, url: `/synthetic/${start+i}.jpg`}))})};
    }
  };
  vm.runInNewContext(source, context);
  return {calls, byteCalls, images, held, metaHeld, windowEvents, context, get: (k, plane = 0) => sets[plane][k], budget: () => vm.runInNewContext('viewerBudget', context), wheel: (deltaY, extra = {}) => {
    let prevented = false;
    sets[0]['.series-frame'].events.wheel({deltaY, deltaX: 0, deltaMode: 0, preventDefault: () => { prevented = true; }, ...extra});
    return prevented;
  }};
}
test('initial metadata and JPEG warmup stay bounded, never a stack', async () => {
  const v = viewer(5000); await settle(); await sleep(220); await settle();
  assert.deepEqual(v.calls, [{index: 0, count: 128}]);
  assert.ok(new Set(v.images).size <= 3);
  assert.ok(v.budget().bytes <= 64 * 1024 * 1024);
});
test('cached transitions and reversal display exact decoded slice', async () => {
  const v = viewer(); await settle(); await sleep(220);
  for (let n = 1; n <= 10; n++) {
    v.get('[data-next]').events.click(); await settle();
    assert.equal(v.get('[data-current-slice]').src, `/synthetic/${n}.jpg`);
    assert.equal(v.get('[data-series-status]').textContent, '');
  }
  assert.ok(v.calls.length <= 2);
  v.get('[data-previous]').events.click(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/9.jpg');
});
test('wheel navigates and preserves zoom/horizontal gestures', async () => {
  const v = viewer(); await settle();
  assert.equal(v.wheel(100), true); await settle();
  assert.equal(v.get('output').value, '2 / 120');
  assert.equal(v.wheel(100, {ctrlKey: true}), false);
  assert.equal(v.wheel(20, {deltaX: 100}), false);
  v.wheel(-100); await settle();
  assert.equal(v.get('output').value, '1 / 120');
});
test('small trackpad motion accumulates and bounds clamp', async () => {
  const v = viewer(2); await settle();
  v.wheel(10); v.wheel(10); v.wheel(10);
  assert.equal(v.get('output').value, '1 / 2');
  v.wheel(10); await settle();
  assert.equal(v.get('output').value, '2 / 2');
  v.wheel(100); await settle();
  assert.equal(v.get('[data-next]').disabled, true);
});
test('single-image series never requests neighbors', async () => {
  const v = viewer(1); await settle(); await sleep(180);
  assert.equal(v.calls.length, 1);
  assert.equal(v.images.length, 1);
  assert.equal(v.get('[data-next]').disabled, true);
});
test('metadata failures are visible and do not cause bulk retry', async () => {
  const v = viewer(100, true); await settle();
  assert.match(v.get('[data-series-status]').textContent, /no disponible/);
  assert.equal(v.calls.length, 1);
});
test('rapid navigation skips stale responses and downloads', async () => {
  const v = viewer();
  for (let n = 0; n < 15; n++) v.get('[data-next]').events.click();
  await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/15.jpg');
  assert.equal(v.get('output').value, '16 / 120');
  assert.ok(v.calls.length <= 2);
  assert.equal(v.images.length, 1);
});
test('old slice remains visible and honestly labelled until new decode finishes', async () => {
  const v = viewer(120, false, true); await settle();
  v.held.shift()(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/0.jpg');
  v.get('[data-next]').events.click(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/0.jpg');
  assert.match(v.get('output').value, /Visible 1.*solicitado 2/);
  assert.match(v.get('[data-series-status]').textContent, /Sigue visible el corte 1/);
  assert.equal(v.get('.series-frame').attrs['aria-busy'], 'true');
  v.held.shift()(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/1.jpg');
  assert.equal(v.get('.series-frame').attrs['aria-busy'], 'false');
});
test('speculation concurrency and memory budget are shared across planes', async () => {
  const v = viewer(5000, false, true, 3); await settle();
  while (v.held.length) { v.held.shift()(); await settle(); }
  await sleep(80); await settle();
  assert.ok(v.budget().active <= 2);
  assert.ok(v.budget().bytes <= 64 * 1024 * 1024);
});

test('failed requested image retains prior slice and renews at most once', async () => {
  const v = viewer(120, false, false, 1, new Set(['/synthetic/1.jpg'])); await settle();
  v.get('[data-next]').events.click(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/0.jpg');
  assert.match(v.get('[data-series-status]').textContent, /no disponible.*Sigue visible el corte 1/);
  assert.equal(v.calls.length, 2);
  assert.equal(v.images.filter(url => url.endsWith('/1.jpg')).length, 2);
});
test('a late decode cannot overwrite the newest requested slice', async () => {
  const v = viewer(120, false, true); await settle();
  v.held.shift()(); await settle();
  v.get('[data-next]').events.click(); await settle();
  v.get('[data-next]').events.click(); await settle();
  v.held.shift()(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/0.jpg');
  v.held.shift()(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/2.jpg');
});

test('failure of an older in-flight image does not poison the newest target', async () => {
  const v = viewer(120, false, true); await settle();
  v.held.shift()(); await settle();
  v.get('[data-next]').events.click(); await settle();
  v.get('[data-next]').events.click(); await settle();
  // Force the older image to reject after the newer request is waiting for it.
  const failOld = v.held.shift();
  // Replace the queued successful load with a rejected decode.
  // This exercises the same rejected foreground promise as a network error.
  const original = v.context.Image.prototype.decode;
  v.context.Image.prototype.decode = function () { return this.src.endsWith('/1.jpg') ? Promise.reject(new Error('stale image failure')) : original.call(this); };
  failOld(); await settle();
  assert.equal(v.calls.length, 1, 'new target must not need metadata renewal');
  v.held.shift()(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/2.jpg');
  assert.equal(v.get('[data-series-status]').textContent, '');
});

test('a stale metadata failure does not block the newest target retry', async () => {
  const v = viewer(120, false, false, 1, new Set(), true);
  v.get('[data-next]').events.click();
  v.get('[data-next]').events.click();
  v.metaHeld.shift()({ok: false}); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/2.jpg');
  assert.equal(v.calls.length, 2);
});

test('stalled foreground and speculative loads time out and release their slots', async () => {
  const v = viewer(120, false, true, 1, new Set(), false, true); await settle();
  v.held.shift()(); await settle();
  // The runner may delay the pump itself. Start the deadline from observed
  // work instead of assuming its 40ms timer ran before a fixed 70ms sleep.
  const deadline = Date.now() + 2000;
  while ((v.images.length < 3 || v.budget().active !== 0) && Date.now() < deadline) {
    await sleep(10); await settle();
  }
  assert.ok(v.images.length >= 3, 'speculative neighbors must have started');
  assert.equal(v.budget().active, 0, 'stalled speculation must release both slots');
  v.get('[data-next]').events.click(); await settle();
  v.get('[data-next]').events.click(); await settle();
  const foregroundDeadline = Date.now() + 2000;
  while (!v.images.includes('/synthetic/2.jpg') && Date.now() < foregroundDeadline) {
    await sleep(10); await settle();
  }
  // Newest requested image starts after stale load timeout, not browser timeout.
  assert.ok(v.images.includes('/synthetic/2.jpg'));
  while (v.held.length) {v.held.shift()(); await settle();}
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/2.jpg');
});
test('back-forward-cache restore reactivates controls and reloads current metadata', async () => {
  const v = viewer(); await settle();
  v.windowEvents.pagehide({persisted: true});
  v.windowEvents.pageshow({persisted: true}); await settle();
  v.get('[data-next]').events.click(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/1.jpg');
  assert.equal(v.get('output').value, '2 / 120');
});

function bytePool(fetch) {
  const context = {document: {querySelectorAll: () => []}, location: {href: 'https://fixture.test'}, URL, Blob, DOMException, AbortController, TypeError, setTimeout, clearTimeout, fetch};
  vm.runInNewContext(source, context);
  return vm.runInNewContext('seriesBytes', context);
}
function byteResponse(size = 32) {
  return {ok: true, headers: new Map([['Content-Type', 'image/jpeg'], ['Content-Length', String(size)]]), body: new ReadableStream({start(controller) {controller.enqueue(new Uint8Array(size));controller.close();}})};
}
test('compressed cache downloads bytes without constructing or decoding Images', async () => {
  let calls = 0;
  const pool = bytePool(async () => {calls++;return byteResponse();});
  const signal = new AbortController().signal;
  const result = await pool.download('/image.jpg', signal);
  assert.equal(result.size, 32);assert.equal(pool.bytes, 32);assert.equal(pool.active, 0);
  await pool.download('/image.jpg', signal);assert.equal(calls, 1);
  pool.clear();assert.equal(pool.bytes, 0);
});
test('compressed cache caps objects and total bytes with bounded eviction', async () => {
  const pool = bytePool(async () => byteResponse(40));pool.limit=64;pool.objectLimit=48;
  const signal = new AbortController().signal;
  await pool.download('/one.jpg', signal);
  await pool.download('/two.jpg', signal);assert.equal(pool.get('/one.jpg'), undefined);assert.equal(pool.bytes, 40);
  pool.objectLimit=16;await assert.rejects(pool.download('/huge.jpg', signal), /limit/);
  assert.equal(pool.active, 0);assert.equal(pool.bytes, 40);
});
test('CORS failure disables byte downloads for that origin, ordinary viewer remains independent', async () => {
  let calls=0;const pool=bytePool(async () => {calls++;throw new TypeError('CORS');});const signal=new AbortController().signal;
  await assert.rejects(pool.download('/one.jpg', signal));await assert.rejects(pool.download('/two.jpg', signal));
  assert.equal(calls,1);assert.equal(pool.active,0);
});
test('cancelled byte download cannot publish bytes after the page was cleared', async () => {
  let done;const pool=bytePool(async () => new Promise(resolve => {done=resolve;}));const controller=new AbortController();
  const pending=pool.download('/one.jpg',controller.signal);controller.abort();done(byteResponse());
  await assert.rejects(pending, /Cancelled/);assert.equal(pool.bytes,0);assert.equal(pool.active,0);
});
test('return to an already decoded cut never waits for an unrelated foreground download', async () => {
  const v=viewer(120,false,true);await settle();v.held.shift()();await settle();
  v.get('[data-next]').events.click();await settle();
  v.get('[data-previous]').events.click();await settle();
  assert.equal(v.get('output').value,'1 / 120');
  assert.equal(v.get('[data-series-status]').textContent,'');
  v.held.shift()();await settle();
  assert.equal(v.get('output').value,'1 / 120');
});
test('clearing compressed bytes aborts pending work without disabling the origin or later downloads', async () => {
  let finish;const pool=bytePool(async () => new Promise(resolve => {finish=resolve;}));const signal=new AbortController().signal;
  const pending=pool.download('/one.jpg',signal);pool.clear();finish(byteResponse());
  await assert.rejects(pending,/Cancelled/);assert.equal(pool.disabled.size,0);assert.equal(pool.bytes,0);
  const next=pool.download('/two.jpg',signal);finish(byteResponse());await next;
  assert.equal(pool.bytes,32);assert.equal(pool.active,0);
});
test('byte transport admits at most three concurrent streaming downloads', async () => {
  const pending=[];const pool=bytePool(async () => new Promise(resolve=>pending.push(resolve)));const signal=new AbortController().signal;
  const a=pool.download('/a.jpg',signal),b=pool.download('/b.jpg',signal),c=pool.download('/c.jpg',signal);
  assert.equal(pool.active,3);assert.equal(await pool.download('/d.jpg',signal),null);
  for(const resolve of pending)resolve(byteResponse());await Promise.all([a,b,c]);assert.equal(pool.active,0);
});
test('streaming limit is enforced even without Content-Length', async () => {
  const pool=bytePool(async () => {const response=byteResponse(48);response.headers.delete('Content-Length');return response;});pool.objectLimit=32;
  await assert.rejects(pool.download('/huge.jpg',new AbortController().signal),/limit/);assert.equal(pool.bytes,0);assert.equal(pool.active,0);
});

test('series template has no manual preparation UI or event handlers', () => {
  const template=fs.readFileSync('blog/templates/blog/_series.html','utf8');
  assert.doesNotMatch(template,/data-prepare|data-cancel-prepare|series-prepare/);
  assert.doesNotMatch(source,/prepareSeries|prepareButton|prepareStatus|cancelButton/);
});
test('automatic byte prefetch still warms 48 upcoming cuts without a button', async () => {
  const v=viewer(120,false,false,1,new Set(),false,false,true);await settle();
  await sleep(1200);await settle();
  assert.equal(v.byteCalls.length,48);
  assert.deepEqual(v.byteCalls.map(u=>Number(u.match(/(\d+)\.jpg/)[1])).sort((a,b)=>a-b),Array.from({length:48},(_,i)=>i+1));
  assert.equal(v.get('output').value,'1 / 120');
  assert.equal(vm.runInNewContext('seriesBytes.bytes',v.context),48*32);
  v.windowEvents.pagehide({persisted:false});
});
test('automatic byte prefetch follows reversal rather than fetching both directions', async () => {
  const v=viewer(120,false,false,1,new Set(),false,false,true);await settle();
  v.get('input').value='51';v.get('input').events.input();await sleep(800);await settle();
  assert.ok(v.byteCalls.includes('/synthetic/74.jpg'));
  assert.ok(!v.byteCalls.includes('/synthetic/26.jpg'));
  v.get('[data-previous]').events.click();await settle();await sleep(800);await settle();
  assert.ok(v.byteCalls.includes('/synthetic/25.jpg'));
  assert.equal(v.get('output').value,'50 / 120');
  assert.ok(v.budget().bytes<=64*1024*1024);
  v.windowEvents.pagehide({persisted:false});
});
