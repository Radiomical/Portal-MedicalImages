const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static-src/js/clinical.js', 'utf8');
const settle = async () => { for (let n = 0; n < 15; n++) await Promise.resolve(); };
function viewer(total = 120, fail = false) {
  class Element {
    constructor() { this.events = {}; this.attrs = {}; this.clientHeight = 400; }
    addEventListener(name, callback, options) { this.events[name] = callback; this.options = options; }
    getAttribute(name) { return this.attrs[name]; }
    removeAttribute(name) { delete this.attrs[name]; }
    set src(value) { this.attrs.src = value; this.complete = true; this.naturalWidth = 8; }
    get src() { return this.attrs.src; }
  }
  const selectors = Object.fromEntries(['.series-controls', 'input', 'output', '[data-previous]', '[data-next]', '.series-frame', '[data-current-slice]', '[data-series-status]'].map(k => [k, new Element()]));
  selectors['.series-controls'].querySelector = k => selectors[k];
  const series = {dataset: {count: String(total), endpoint: '/synthetic/slices/'}, querySelector: k => selectors[k], getAttribute: () => 'Synthetic series'};
  const calls = [], images = [];
  const context = {
    document: {querySelectorAll: () => [series]}, AbortController,
    setTimeout, clearTimeout, Date, Image: class {
      set src(value) { images.push(value); queueMicrotask(() => this.onload?.()); }
    },
    fetch: async (url, {signal}) => {
      const index = Number(url.split('=')[1]); calls.push(index);
      if (signal.aborted) throw Object.assign(new Error(), {name: 'AbortError'});
      if (fail) return {ok: false};
      return {ok: true, json: async () => ({index, ttl: 300, images: Array.from({length: Math.min(2, total - index)}, (_, i) => ({index: index + i, url: `/synthetic/${index+i}.jpg`}))})};
    }
  };
  vm.runInNewContext(source, context);
  return {calls, images, get: k => selectors[k], wheel: (deltaY, extra = {}) => {
    let prevented = false;
    selectors['.series-frame'].events.wheel({deltaY, deltaX: 0, deltaMode: 0, preventDefault: () => { prevented = true; }, ...extra});
    return prevented;
  }};
}
test('initial prefetch is bounded to three neighbors, not the stack', async () => {
  const v = viewer(5000); await settle();
  assert.deepEqual(v.calls, [0, 2]);
  assert.equal(new Set(v.images).size, 3);
});
test('cached transitions refill the window and avoid loading flashes', async () => {
  const v = viewer(); await settle();
  for (let n = 1; n <= 10; n++) {
    v.get('[data-next]').events.click(); await settle();
    assert.equal(v.get('[data-current-slice]').src, `/synthetic/${n}.jpg`);
    assert.equal(v.get('[data-series-status]').textContent, '');
  }
  assert.ok(Math.max(...v.calls) <= 13);
  v.get('[data-previous]').events.click(); await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/9.jpg');
});
test('wheel navigates inside frame and preserves browser zoom', async () => {
  const v = viewer(); await settle();
  assert.equal(v.wheel(100), true); await settle();
  assert.equal(v.get('output').value, '2 / 120');
  assert.equal(v.wheel(100, {ctrlKey: true}), false);
  assert.equal(v.wheel(20, {deltaX: 100}), false);
  assert.equal(v.get('output').value, '2 / 120');
  v.wheel(-100); await settle();
  assert.equal(v.get('output').value, '1 / 120');
});
test('wheel accumulates small trackpad motion and clamps at bounds', async () => {
  const v = viewer(2); await settle();
  v.wheel(10); v.wheel(10); v.wheel(10);
  assert.equal(v.get('output').value, '1 / 2');
  v.wheel(10); await settle();
  assert.equal(v.get('output').value, '2 / 2');
  v.wheel(100); await settle();
  assert.equal(v.get('output').value, '2 / 2');
  assert.equal(v.get('[data-next]').disabled, true);
});
test('single-image series does not fetch beyond end', async () => {
  const v = viewer(1); await settle();
  assert.deepEqual(v.calls, [0]);
  assert.equal(v.get('[data-next]').disabled, true);
});
test('foreground errors remain visible and do not trigger bulk retries', async () => {
  const v = viewer(100, true); await settle();
  assert.match(v.get('[data-series-status]').textContent, /no disponible/);
  assert.deepEqual(v.calls, [0]);
});
test('rapid navigation does not show a stale response', async () => {
  const v = viewer();
  v.get('[data-next]').events.click();
  v.get('[data-next]').events.click();
  await settle();
  assert.equal(v.get('[data-current-slice]').src, '/synthetic/2.jpg');
  assert.equal(v.get('output').value, '3 / 120');
});
