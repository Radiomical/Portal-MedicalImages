"use strict";
// Keep a small sliding window, never an entire stack of signed URLs or images.
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
  let index = 0;
  let generation = 0;
  let controller;
  let warming;
  let renewalAttempted = false;
  const cache = new Map();
  const fresh = (entry) => entry && entry.expires > Date.now() + 10000;
  const prune = () => {
    for (const [key, entry] of cache) {
      if (key < index - 1 || key > index + 3 || !fresh(entry)) cache.delete(key);
    }
  };
  const remember = (data, requested) => {
    if (data.index !== requested || !Array.isArray(data.images) ||
        !data.images.length || data.images.length > 2 ||
        !Number.isFinite(data.ttl) || data.ttl <= 0 ||
        data.images.some((item, offset) => item.index !== requested + offset ||
          item.index >= total || typeof item.url !== "string" || !item.url)) {
      throw new Error("Invalid image response");
    }
    data.images.forEach((item) => {
      const old = cache.get(item.index);
      if (fresh(old) && old.url === item.url) return;
      cache.set(item.index, {url: item.url, expires: Date.now() + data.ttl * 1000});
    });
    prune();
  };
  const request = async (requested, signal) => {
    const response = await fetch(`${series.dataset.endpoint}?index=${requested}`, {
      signal, credentials: "same-origin", cache: "no-store"
    });
    if (!response.ok) throw new Error("Image unavailable");
    return response.json();
  };
  const warmImage = (entry) => {
    if (!fresh(entry) || entry.preload) return;
    const preload = new Image();
    entry.preload = preload;
    preload.onload = () => { entry.loaded = true; };
    preload.onerror = () => { entry.preload = null; entry.loaded = false; };
    preload.src = entry.url;
  };
  const warmWindow = async () => {
    // One background metadata request at a time. Refill on cached transitions too.
    if (warming) return;
    const token = generation;
    const background = new AbortController();
    warming = background;
    try {
      const start = index;
      for (let target = start + 1; target <= Math.min(total - 1, start + 3); target++) {
        if (token !== generation) return;
        if (!fresh(cache.get(target))) {
          const data = await request(target, background.signal);
          if (token !== generation) return;
          remember(data, target);
        }
        warmImage(cache.get(target));
      }
      warmImage(cache.get(index - 1));
    } catch (error) {
      // A speculative failure must not hide the current image or block navigation.
    } finally {
      if (warming === background) warming = null;
    }
  };
  const display = (entry) => {
    image.src = entry.url;
    image.alt = `${series.getAttribute("aria-label")} - corte ${index + 1} de ${total}`;
    image.hidden = false;
    if (entry.loaded || (image.complete && image.naturalWidth > 0)) status.textContent = "";
    warmWindow();
  };
  const show = async (value, renew = false) => {
    const target = Math.max(0, Math.min(total - 1, value));
    if (!renew && target === index && image.getAttribute("src")) return;
    index = target;
    if (!renew) renewalAttempted = false;
    const token = ++generation;
    controller?.abort();
    warming?.abort();
    warming = null;
    prune();
    range.value = String(index + 1);
    output.value = `${index + 1} / ${total}`;
    previous.disabled = index === 0;
    next.disabled = index === total - 1;
    const current = cache.get(index);
    // A decoded neighbor can swap directly, without flashing the loading label.
    status.textContent = !renew && fresh(current) && current.loaded ? "" : "Cargando imagen…";
    image.hidden = true;
    image.removeAttribute("src");
    if (!renew && fresh(current)) {
      display(current);
      return;
    }
    controller = new AbortController();
    const requested = index;
    try {
      const data = await request(requested, controller.signal);
      if (token !== generation) return;
      if (renew) cache.delete(requested);
      remember(data, requested);
      display(cache.get(requested));
    } catch (error) {
      if (token !== generation || error.name === "AbortError") return;
      status.textContent = "Imagen no disponible. Cambia de corte para volver a intentarlo.";
    }
  };
  image.addEventListener("load", () => { status.textContent = ""; });
  image.addEventListener("error", () => {
    if (!image.getAttribute("src")) return;
    if (!renewalAttempted) {
      renewalAttempted = true;
      show(index, true);
    } else {
      status.textContent = "Imagen no disponible. Cambia de corte para volver a intentarlo.";
    }
  });
  previous.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  let scrubTimer;
  range.addEventListener("input", () => {
    clearTimeout(scrubTimer);
    scrubTimer = setTimeout(() => show(Number(range.value) - 1), 80);
  });
  let wheelDelta = 0;
  let wheelTime = 0;
  frame.addEventListener("wheel", (event) => {
    // Preserve browser zoom and horizontal trackpad gestures.
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
  controls.hidden = false;
  show(0);
});
