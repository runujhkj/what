const { createCaptionLayout } = require("./caption_box_layout");
const { createCaptionView } = require("./caption_box_view");

function captionBoxRuntime(createLayout, createView) {
  const params = new URLSearchParams(location.search);
  const number = (key, fallback, min, max) => {
    const value = params.has(key) ? Number(params.get(key)) : fallback;
    return Math.max(min, Math.min(max, Number.isFinite(value) ? value : fallback));
  };
  const fontSize = number("fontSize", 32, 8, 160);
  const padding = number("padding", 12, 0, 200);
  const frame = document.getElementById("frame");
  const probe = document.getElementById("measure");
  const text = document.getElementById("text");
  const lineHeight = fontSize * 1.25;
  frame.style.fontSize = `${fontSize}px`;
  frame.style.lineHeight = `${lineHeight}px`;
  frame.style.padding = `${padding}px`;
  frame.style.fontFamily = params.get("fontFamily") || "sans-serif";
  frame.style.color = params.get("textColor") || "white";
  frame.style.backgroundColor = params.get("bgColor") || "rgba(0,0,0,0.6)";
  const layout = createLayout((value) => {
    probe.textContent = value;
    return probe.getBoundingClientRect().width;
  });
  let latest = "";
  let stream = null;
  const view = createView(text, {
    lineHeight,
    reducedMotion: typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches,
  });
  function render(reflow = false) {
    const width = Math.max(0, frame.clientWidth - padding * 2);
    const height = Math.max(0, frame.clientHeight - padding * 2);
    const result = layout.update(latest, { width, maxLines: Math.floor(height / lineHeight), reflow, stream });
    text.style.height = `${Math.floor(height / lineHeight) * lineHeight}px`;
    view.render(result.rows, { reset: result.reset });
    frame.dataset.hiddenLines = result.hiddenLines;
  }
  new ResizeObserver(() => render()).observe(frame);
  document.fonts.ready.then(() => render(true));
  document.fonts.addEventListener("loadingdone", () => render(true));
  if (params.get("demo") === "1") {
    latest = "This caption box keeps its font size when you resize it. Narrow the box to wrap the words, or change its height to show more lines.";
    render();
  } else {
    const source = params.get("box") === "desktop" ? "desktop" : "mic";
    const events = new EventSource(`/events?box=${source}`);
    events.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        // URL/viewport own geometry. Stream updates carry content, never font or box size.
        latest = String(payload.text || "");
        stream = payload.captionStream || null;
        render();
      } catch (_) { /* A malformed event must not replace visible text with protocol data. */ }
    };
  }
}

function buildCaptionBoxHtml() {
  return `<!doctype html><html><head><meta charset="utf-8"><title>What caption box</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}
#frame{position:relative;box-sizing:border-box;width:100%;height:100%;overflow:hidden}
#text{position:relative;width:100%;overflow:hidden}
.caption-line{position:absolute;top:0;left:0;width:100%;white-space:pre;overflow:hidden;will-change:transform}
#measure{position:absolute;left:0;top:0;width:max-content;max-width:none;visibility:hidden;white-space:pre;pointer-events:none;font:inherit}
</style></head><body><div id="frame"><span id="measure"></span><div id="text"></div></div>
<script>(${captionBoxRuntime.toString()})(${createCaptionLayout.toString()}, ${createCaptionView.toString()});</script></body></html>`;
}
module.exports = { buildCaptionBoxHtml };
