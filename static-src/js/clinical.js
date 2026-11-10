"use strict";
// Metadata: <=21 URLs per series. Decoded speculation: <=64 MiB estimated across
// all series, <=2 concurrent speculative images. Visible images/browser HTTP
// cache are outside this estimate; the browser controls their actual allocation.
const viewerBudget = {bytes: 0, active: 0, waiters: new Set(), limit: 64 * 1024 * 1024};
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
  let index = 0, displayed = -1, generation = 0, direction = 1;
  let lastMove = 0, fastUntil = 0, metadataPending, foregroundPending;
  let idleTimer, pumpTimer, disposed = false;
  let imageBytes = 4 * 1024 * 1024;
  const fresh = (entry) => entry && entry.expires > Date.now() + 10000;
  const windowSize = () => Date.now() < fastUntil ? 16 : 8;
  const bounds = () => direction > 0 ? [Math.max(0, index - 4), Math.min(total - 1, index + windowSize())] :
    [Math.max(0, index - windowSize()), Math.min(total - 1, index + 4)];
  const release = (entry) => {
    if (entry.reserved) viewerBudget.bytes -= entry.reserved;
    entry.reserved = 0;
    entry.decoded = null;
  };
  const prune = () => {
    const [low, high] = bounds();
    for (const [key, entry] of cache) {
      if (key < low || key > high || !fresh(entry)) {
        release(entry);
        cache.delete(key);
      }
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
    const ahead = windowSize();
    const before = direction > 0 ? 4 : ahead;
    const after = direction > 0 ? ahead : 4;
    const start = Math.max(0, target - before);
    const task = (async () => {
      const response = await fetch(`${series.dataset.endpoint}?index=${target}&before=${before}&after=${after}`, {
        credentials: "same-origin", cache: "no-store"
      });
      if (!response.ok) throw new Error("Image unavailable");
      const data = await response.json();
      if (data.index !== target || data.total !== total || !Array.isArray(data.images) ||
          data.images.length !== Math.min(total, target + after + 1) - start || data.images.length > 21 ||
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
    try { await task; } finally { if (metadataPending === task) metadataPending = null; }
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
    const task = (async () => {
      try {
        const loaded = new Promise((resolve, reject) => {
          preload.onload = resolve;
          preload.onerror = () => reject(new Error("Image unavailable"));
        });
        preload.src = entry.url;
        await loaded;
        if (preload.decode) await preload.decode();
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
    // At most six warmed neighbors per series, direction first; metadata can
    // look farther ahead without downloading those JPEGs.
    const targets = [];
    for (let n = 1; n <= 6; n++) targets.push(index + direction * n);
    targets.push(index - direction, index - direction * 2);
    let warmed = 0;
    for (const target of targets) {
      if (target < 0 || target >= total) continue;
      const entry = cache.get(target);
      if (!fresh(entry) || entry.failed || entry.noWarm) continue;
      if (++warmed > 6) break;
      if (!entry.decoded && !entry.loading) {
        const task = decode(entry, true);
        task?.catch(() => { entry.failed = true; }).finally(schedulePump);
      }
    }
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
      if (metadataPending) await metadataPending;
      if (token !== generation || disposed) return;
      if (renew || !fresh(cache.get(index))) await fetchWindow(index);
      if (token !== generation || disposed) return;
      const requested = index;
      const entry = cache.get(requested);
      // Only one demanded download per series. Rapid changes wait for it and
      // then select the newest target, instead of starting many stale GETs.
      if (foregroundPending) await foregroundPending.catch(() => {});
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
  const show = (value) => {
    const target = Math.max(0, Math.min(total - 1, value));
    if (target === index && displayed >= 0) return;
    const now = Date.now();
    if (target !== index) {
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
    viewerBudget.waiters.delete(schedulePump);
    clearTimeout(idleTimer); clearTimeout(pumpTimer); clearTimeout(scrubTimer);
    for (const entry of cache.values()) release(entry);
    cache.clear();
  });
  viewerBudget.waiters.add(schedulePump);
  controls.hidden = false;
  show(0);
});
