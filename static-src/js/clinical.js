"use strict";
// Metadata: <=128 URLs per request, bounded sliding cache. Decoded speculation: <=64 MiB estimated across
// all series, <=2 concurrent speculative images. Visible images/browser HTTP
// cache are outside this estimate; the browser controls their actual allocation.
const viewerBudget = {bytes: 0, active: 0, waiters: new Set(), limit: 64 * 1024 * 1024};
// Compressed bytes and decoded pixels are separate, bounded caches. Blob URLs
// live only as long as their decoded Image; downloads never call Image.decode.
const seriesBytes = {
  limit: 96 * 1024 * 1024, objectLimit: 8 * 1024 * 1024, bytes: 0,
  active: 0, entries: new Map(), pending: new Map(), activeSeries: null,
  disabled: new Set(),
  get(url) {
    const value = this.entries.get(url);
    if (value) { this.entries.delete(url); this.entries.set(url, value); }
    return value;
  },
  clear() { this.entries.clear(); this.bytes = 0; for (const item of this.pending.values()) item.abort(); },
  async download(url, signal) {
    if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    const cached = this.get(url);
    if (cached) return cached;
    if (this.active >= 3 || this.pending.has(url)) return null;
    const origin = new URL(url, location.href).origin;
    if (this.disabled.has(origin)) throw new Error('Byte cache unavailable');
    const abort = new AbortController();
    const cancel = () => abort.abort();
    signal.addEventListener('abort', cancel, {once: true});
    this.pending.set(url, abort); this.active++;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; cancel(); }, 12000);
    try {
      const response = await fetch(url, {mode: 'cors', credentials: 'omit', cache: 'force-cache', signal: abort.signal, priority: 'low'});
      if (!response.ok || !response.headers.get('Content-Type')?.toLowerCase().startsWith('image/')) throw new Error('Invalid image response');
      const declared = Number(response.headers.get('Content-Length') || 0);
      if (declared > this.objectLimit) throw new Error('Image exceeds download limit');
      const reader = response.body?.getReader();
      if (!reader) throw new Error('Streaming download unavailable');
      const chunks = []; let size = 0;
      try {
        while (true) {
          const chunk = await reader.read(); if (chunk.done) break;
          size += chunk.value.byteLength;
          if (size > this.objectLimit) throw new Error('Image exceeds download limit');
          chunks.push(chunk.value);
        }
      } finally { await reader.cancel().catch(() => {}); }
      if (signal.aborted || abort.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
      if (!size) throw new Error('Empty image response');
      while (this.bytes + size > this.limit && this.entries.size) {
        const oldest = this.entries.keys().next().value;
        this.bytes -= this.entries.get(oldest).size; this.entries.delete(oldest);
      }
      const blob = new Blob(chunks, {type: response.headers.get('Content-Type')});
      this.entries.set(url, blob); this.bytes += size;
      return blob;
    } catch (error) {
      // A failed CORS policy must not break the ordinary <img> path, nor be
      // retried continuously for every image on the same origin.
      if (error instanceof TypeError && !abort.signal.aborted) this.disabled.add(origin);
      if (timedOut) throw new Error('Byte download timeout');
      throw error;
    } finally {
      clearTimeout(timeout); signal.removeEventListener('abort', cancel);
      this.pending.delete(url); this.active--;
    }
  }
};

document.querySelectorAll("[data-series]").forEach((series) => {
  const controls = series.querySelector(".series-controls");
  const range = controls.querySelector("input");
  const output = controls.querySelector("output");
  const previous = controls.querySelector("[data-previous]");
  const next = controls.querySelector("[data-next]");
  const frame = series.querySelector(".series-frame");
  const image = series.querySelector("[data-current-slice]");
  const status = series.querySelector("[data-series-status]");
  const total = Number(series.dataset.count);
  if (!Number.isSafeInteger(total) || total < 1) return;
  const cache = new Map();
  if (!seriesBytes.activeSeries) seriesBytes.activeSeries = series;
  let downloads = new AbortController(), byteTimer;
  let index = 0, displayed = -1, generation = 0, direction = 1;
  let lastMove = 0, fastUntil = 0, metadataPending, foregroundPending;
  let idleTimer, pumpTimer, disposed = false;
  let imageBytes = 4 * 1024 * 1024;
  const fresh = (entry) => entry && entry.expires > Date.now() + 10000;
  const windowSize = () => Date.now() < fastUntil ? 64 : 32;
  const bounds = () => direction > 0 ? [Math.max(0, index - 4), Math.min(total - 1, index + windowSize())] :
    [Math.max(0, index - windowSize()), Math.min(total - 1, index + 4)];
  const release = (entry) => {
    if (entry.reserved) viewerBudget.bytes -= entry.reserved;
    entry.reserved = 0;
    entry.decoded = null;
    if (entry.blobUrl) URL.revokeObjectURL(entry.blobUrl);
    entry.blobUrl = null;
  };
  const prune = () => {
    const [low, high] = bounds();
    for (const [key, entry] of cache) {
      if (key < index - 128 || key > index + 127 || !fresh(entry)) {
        release(entry);
        cache.delete(key);
      } else if (key < low || key > high) release(entry);
    }
    // Any former visible image retained for reuse must rejoin the budget.
    for (const [key, entry] of cache) {
      if (key !== displayed && entry.decoded && !entry.reserved) {
        const bytes = entry.decoded.naturalWidth * entry.decoded.naturalHeight * 4;
        if (viewerBudget.bytes + bytes <= viewerBudget.limit) {
          entry.reserved = bytes;
          viewerBudget.bytes += bytes;
        } else release(entry);
      }
    }
    // Visible/current images do not consume the speculative budget.
    const visible = cache.get(displayed);
    if (visible?.reserved) { viewerBudget.bytes -= visible.reserved; visible.reserved = 0; }
  };
  const fetchWindow = async (target) => {
    if (metadataPending) return metadataPending;
    const count = 128;
    const start = Math.max(0, Math.min(target - 24, total - count));
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 8000);
    const task = (async () => {
      const response = await fetch(`${series.dataset.endpoint}?index=${start}&count=${count}`, {
        signal: abort.signal, credentials: "same-origin", cache: "no-store"
      });
      if (!response.ok) throw new Error("Image unavailable");
      const data = await response.json();
      if (data.index !== start || data.total !== total || !Array.isArray(data.images) ||
          data.images.length !== Math.min(count, total - start) || data.images.length > 128 ||
          !Number.isFinite(data.ttl) || data.ttl <= 0 ||
          data.images.some((item, offset) => item.index !== start + offset || typeof item.url !== "string" || !item.url)) {
        throw new Error("Invalid image response");
      }
      if (disposed) return;
      data.images.forEach((item) => {
        const old = cache.get(item.index);
        if (fresh(old) && old.url === item.url) return;
        if (old) release(old);
        cache.set(item.index, {url: item.url, expires: Date.now() + data.ttl * 1000});
      });
      prune();
    })();
    metadataPending = task;
    try { await task; } finally { clearTimeout(timeout); if (metadataPending === task) metadataPending = null; }
  };
  const decode = (entry, speculative = false) => {
    if (entry.decoded) return Promise.resolve(entry.decoded);
    if (entry.loading) return entry.loading;
    if (speculative) {
      if (viewerBudget.active >= 2 || viewerBudget.bytes + imageBytes > viewerBudget.limit) return null;
      viewerBudget.active++;
      entry.reserved = imageBytes;
      viewerBudget.bytes += entry.reserved;
    }
    const preload = new Image();
    preload.decoding = "async";
    preload.fetchPriority = speculative ? "low" : "high";
    let loadTimeout;
    const task = (async () => {
      try {
        const loaded = new Promise((resolve, reject) => {
          preload.onload = resolve;
          preload.onerror = () => reject(new Error("Image unavailable"));
        });
        const blob = seriesBytes.get(entry.url);
        if (blob) entry.blobUrl = URL.createObjectURL(blob);
        preload.src = entry.blobUrl || entry.url;
        const deadline = new Promise((resolve, reject) => {
          loadTimeout = setTimeout(() => {
            preload.onload = null; preload.onerror = null;
            preload.removeAttribute("src");
            reject(new Error("Image load timeout"));
          }, 8000);
        });
        await Promise.race([(async () => { await loaded; if (preload.decode) await preload.decode(); })(), deadline]);
        const bytes = preload.naturalWidth * preload.naturalHeight * 4;
        if (!Number.isFinite(bytes) || bytes <= 0) throw new Error("Invalid image size");
        // Do not retain a speculative large image or one evicted during a jump.
        const retained = !disposed && [...cache.values()].includes(entry);
        if (speculative && (!retained || viewerBudget.bytes - entry.reserved + bytes > viewerBudget.limit)) {
          release(entry);
          entry.noWarm = true;
          return preload;
        }
        if (entry.reserved) { viewerBudget.bytes += bytes - entry.reserved; entry.reserved = bytes; }
        if (retained) entry.decoded = preload;
        return preload;
      } catch (error) {
        release(entry);
        throw error;
      } finally {
        clearTimeout(loadTimeout);
        entry.loading = null;
        if (speculative) {
          viewerBudget.active--;
          for (const wake of viewerBudget.waiters) wake();
        }
      }
    })();
    entry.loading = task;
    return task;
  };
  const schedulePump = () => {
    clearTimeout(pumpTimer);
    if (!disposed) pumpTimer = setTimeout(pump, 40);
  };
  const pump = () => {
    if (disposed) return;
    prune();
    // Decode only two near neighbors of the active series. Compressed-byte
    // prefetch can look farther ahead without pinning decoded pixel memory.
    if (seriesBytes.activeSeries !== series) return;
    scheduleBytes();
    const targets = [];
    for (let n = 1; n <= 2; n++) targets.push(index + direction * n);
    targets.push(index - direction, index - direction * 2);
    let warmed = 0;
    for (const target of targets) {
      if (target < 0 || target >= total) continue;
      const entry = cache.get(target);
      if (!fresh(entry) || entry.failed || entry.noWarm) continue;
      if (++warmed > 2) break;
      if (!entry.decoded && !entry.loading) {
        const task = decode(entry, true);
        task?.catch(() => { entry.failed = true; }).finally(schedulePump);
      }
    }
  };
  const scheduleBytes = () => {
    clearTimeout(byteTimer);
    if (disposed || seriesBytes.activeSeries !== series) return;
    byteTimer = setTimeout(async () => {
      const candidates = [];
      for (let n = 1; n <= 48; n++) {
        const entry = cache.get(index + direction * n);
        if (fresh(entry) && !entry.byteFailed && !seriesBytes.get(entry.url)) candidates.push(entry);
      }
      const batch = candidates.slice(0, 3);
      await Promise.all(batch.map(async entry => {
        try { await seriesBytes.download(entry.url, downloads.signal); }
        catch (error) { if (error.name !== 'AbortError') entry.byteFailed = true; }
      }));
      if (batch.length && !disposed && !downloads.signal.aborted &&
          !seriesBytes.disabled.size) scheduleBytes();
    }, 50);
  };
  const refill = () => {
    clearTimeout(idleTimer);
    if (disposed) return;
    idleTimer = setTimeout(async () => {
      const target = Math.max(0, Math.min(total - 1, index + direction * Math.ceil(windowSize() / 2)));
      if (!fresh(cache.get(target))) {
        try { await fetchWindow(index); } catch (error) { /* foreground owns visible errors */ }
      }
      schedulePump();
    }, 120);
  };
  const pendingLabel = () => {
    output.value = displayed >= 0 ? `Visible ${displayed + 1} / ${total}; solicitado ${index + 1}` : `${index + 1} / ${total}`;
    status.textContent = displayed >= 0 ? `Cargando corte ${index + 1}… Sigue visible el corte ${displayed + 1}.` : `Cargando corte ${index + 1}…`;
    frame.setAttribute("aria-busy", "true");
  };
  const present = async (token, renew = false) => {
    try {
      if (metadataPending && (renew || !fresh(cache.get(index)))) await metadataPending.catch(() => {});
      if (token !== generation || disposed) return;
      if (renew || !fresh(cache.get(index))) await fetchWindow(index);
      if (token !== generation || disposed) return;
      const requested = index;
      const entry = cache.get(requested);
      // Only one demanded download per series. Rapid changes wait for it and
      // then select the newest target, instead of starting many stale GETs.
      if (foregroundPending && !entry.decoded) await foregroundPending.catch(() => {});
      if (token !== generation || disposed) return;
      const task = decode(entry);
      foregroundPending = task;
      let ready;
      try { ready = await task; }
      finally { if (foregroundPending === task) foregroundPending = null; }
      if (token !== generation || disposed) { schedulePump(); return; }
      image.src = ready.src;
      image.alt = `${series.getAttribute("aria-label")} - corte ${requested + 1} de ${total}`;
      image.hidden = false;
      imageBytes = ready.naturalWidth * ready.naturalHeight * 4;
      displayed = requested;
      output.value = `${displayed + 1} / ${total}`;
      status.textContent = "";
      frame.setAttribute("aria-busy", "false");
      prune();
      schedulePump();
      refill();
    } catch (error) {
      if (token !== generation || disposed) return;
      if (!renew && fresh(cache.get(index))) {
        const old = cache.get(index);
        release(old);
        cache.delete(index);
        await present(token, true);
        return;
      }
      status.textContent = displayed >= 0 ? `Corte ${index + 1} no disponible. Sigue visible el corte ${displayed + 1}.` : "Imagen no disponible. Cambia de corte para volver a intentarlo.";
      frame.setAttribute("aria-busy", "false");
    }
  };
  const show = (value, force = false) => {
    const target = Math.max(0, Math.min(total - 1, value));
    if (!force && target === index && displayed >= 0) return;
    const now = Date.now();
    if (target !== index) {
      seriesBytes.activeSeries = series;
      if (Math.abs(target - index) > 16 || Math.sign(target - index) !== direction) {
        downloads.abort(); downloads = new AbortController();
      }
      direction = Math.sign(target - index);
      if (now - lastMove < 180) fastUntil = now + 1000;
      lastMove = now;
    }
    index = target;
    const token = ++generation;
    prune();
    range.value = String(index + 1);
    previous.disabled = index === 0;
    next.disabled = index === total - 1;
    pendingLabel();
    present(token);
    refill();
  };
  previous.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  let scrubTimer;
  range.addEventListener("input", () => {
    clearTimeout(scrubTimer);
    scrubTimer = setTimeout(() => show(Number(range.value) - 1), 80);
  });
  let wheelDelta = 0, wheelTime = 0;
  frame.addEventListener("wheel", (event) => {
    if (event.ctrlKey || event.metaKey || Math.abs(event.deltaX) > Math.abs(event.deltaY) || !event.deltaY) return;
    event.preventDefault();
    const now = Date.now();
    if (now - wheelTime > 180 || Math.sign(event.deltaY) !== Math.sign(wheelDelta)) wheelDelta = 0;
    wheelDelta += event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? frame.clientHeight : 1);
    wheelTime = now;
    if (Math.abs(wheelDelta) < 40) return;
    const step = Math.sign(wheelDelta);
    wheelDelta = 0;
    show(index + step);
  }, {passive: false});
  frame.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      show(index + (event.key === "ArrowRight" ? 1 : -1));
    }
  });
  window.addEventListener("pagehide", () => {
    disposed = true;
    downloads.abort();
    clearTimeout(byteTimer);
    seriesBytes.clear();
    viewerBudget.waiters.delete(schedulePump);
    clearTimeout(idleTimer); clearTimeout(pumpTimer); clearTimeout(scrubTimer);
    for (const entry of cache.values()) release(entry);
    cache.clear();
  });
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    disposed = false;
    downloads = new AbortController();
    viewerBudget.waiters.add(schedulePump);
    show(index, true);
  });
  viewerBudget.waiters.add(schedulePump);
  controls.hidden = false;
  show(0);
});
