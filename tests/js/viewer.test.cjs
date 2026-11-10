const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static-src/js/clinical.js', 'utf8');
const settle = async () => { for (let n = 0; n < 45; n++) await Promise.resolve(); };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function viewer(total = 120, fail = false, holdImages = false, planes = 1, failures = new Set()) {
  const sets = [], calls = [], images = [], held = [];
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
    document: {querySelectorAll: () => series}, window: {addEventListener() {}},
    setTimeout: (fn, ms) => setTimeout(fn, ms).unref(), clearTimeout, Date,
    Image: class {
      constructor() { this.naturalWidth = 512; this.naturalHeight = 512; }
      set src(value) { this.url = value; images.push(value); if (failures.has(value)) queueMicrotask(() => this.onerror?.()); else if (holdImages) held.push(() => this.onload?.()); else queueMicrotask(() => this.onload?.()); }
      get src() { return this.url; }
      decode() { return Promise.resolve(); }
    },
    fetch: async url => {
      const u = new URL(url, 'http://synthetic.local');
      const index = Number(u.searchParams.get('index'));
      const before = Number(u.searchParams.get('before'));
      const after = Number(u.searchParams.get('after'));
      calls.push({index, before, after});
      if (fail) return {ok: false};
      const start = Math.max(0, index - before), end = Math.min(total, index + after + 1);
      return {ok: true, json: async () => ({index, total, ttl: 300, images: Array.from({length: end - start}, (_, i) => ({index: start + i, url: `/synthetic/${start+i}.jpg`}))})};
    }
  };
  vm.runInNewContext(source, context);
  return {calls, images, held, context, get: (k, plane = 0) => sets[plane][k], budget: () => vm.runInNewContext('viewerBudget', context), wheel: (deltaY, extra = {}) => {
    let prevented = false;
    sets[0]['.series-frame'].events.wheel({deltaY, deltaX: 0, deltaMode: 0, preventDefault: () => { prevented = true; }, ...extra});
    return prevented;
  }};
}
test('initial metadata and JPEG warmup stay bounded, never a stack', async () => {
  const v = viewer(5000); await settle(); await sleep(220); await settle();
  assert.deepEqual(v.calls, [{index: 0, before: 4, after: 8}]);
  assert.ok(new Set(v.images).size <= 7);
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
