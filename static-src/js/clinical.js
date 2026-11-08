"use strict";
// Each image series owns its controls. No diagnostic processing is applied.
document.querySelectorAll("[data-series]").forEach((series) => {
  const images = Array.from(series.querySelectorAll("[data-slice]"));
  const controls = series.querySelector(".series-controls");
  const range = controls.querySelector("input");
  const output = controls.querySelector("output");
  const previous = controls.querySelector("[data-previous]");
  const next = controls.querySelector("[data-next]");
  const frame = series.querySelector(".series-frame");
  if (!images.length) return;
  let index = 0;
  const show = (value) => {
    index = Math.max(0, Math.min(images.length - 1, value));
    images.forEach((image, i) => { image.hidden = i !== index; });
    range.value = String(index + 1);
    output.value = `${index + 1} / ${images.length}`;
    previous.disabled = index === 0;
    next.disabled = index === images.length - 1;
  };
  previous.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  range.addEventListener("input", () => show(Number(range.value) - 1));
  frame.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      show(index + (event.key === "ArrowRight" ? 1 : -1));
    }
  });
  controls.hidden = false;
  show(0);
});
