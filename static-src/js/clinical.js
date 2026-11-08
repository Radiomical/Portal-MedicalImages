"use strict";
// One displayed image plus one adjacent prefetch per series. No signed stack.
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
  let prefetch;
  let renewalAttempted = false;
  const cache = new Map();
  const fresh = (entry) => entry && entry.expires > Date.now() + 10000;
  const display = (entry) => {
    image.hidden = false;
    image.src = entry.url;
    image.alt = `${series.getAttribute("aria-label")} slice ${index + 1} of ${total}`;
  };
  const warmNext = () => {
    const adjacent = cache.get(index + 1);
    if (fresh(adjacent)) {
      prefetch = new Image();
      prefetch.src = adjacent.url;
    }
  };
  const show = async (value, renew = false) => {
    index = Math.max(0, Math.min(total - 1, value));
    if (!renew) renewalAttempted = false;
    const token = ++generation;
    controller?.abort();
    prefetch = null;
    range.value = String(index + 1);
    output.value = `${index + 1} / ${total}`;
    previous.disabled = index === 0;
    next.disabled = index === total - 1;
    status.textContent = "Loading image…";
    image.hidden = true;
    // Remove old src so a late error from the previous image cannot renew it.
    image.removeAttribute("src");
    const current = cache.get(index);
    if (!renew && fresh(current)) {
      display(current);
      warmNext();
      return;
    }
    controller = new AbortController();
    const requested = index;
    try {
      const response = await fetch(`${series.dataset.endpoint}?index=${requested}`, {
        signal: controller.signal, credentials: "same-origin", cache: "no-store"
      });
      if (!response.ok) throw new Error("Image unavailable");
      const data = await response.json();
      if (token !== generation) return;
      if (data.index !== requested || !Array.isArray(data.images) || data.images.length > 2 || !data.images.length) {
        throw new Error("Invalid image response");
      }
      cache.clear();
      data.images.forEach((item) => cache.set(item.index, {
        url: item.url, expires: Date.now() + data.ttl * 1000
      }));
      display(cache.get(requested));
      warmNext();
    } catch (error) {
      if (token !== generation || error.name === "AbortError") return;
      status.textContent = "Image unavailable. Change slice to try again.";
    }
  };
  image.addEventListener("load", () => { status.textContent = ""; });
  image.addEventListener("error", () => {
    if (!image.getAttribute("src")) return;
    if (!renewalAttempted) {
      renewalAttempted = true;
      show(index, true);
    } else {
      status.textContent = "Image unavailable. Change slice to try again.";
    }
  });
  previous.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  let scrubTimer;
  range.addEventListener("input", () => {
    clearTimeout(scrubTimer);
    scrubTimer = setTimeout(() => show(Number(range.value) - 1), 80);
  });
  frame.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      show(index + (event.key === "ArrowRight" ? 1 : -1));
    }
  });
  controls.hidden = false;
  show(0);
});
