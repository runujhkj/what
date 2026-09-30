const { buildCaptionBoxHtml } = require("./caption_box_page");
const { buildCaptionBoxSettingsHtml } = require("./caption_box_settings");

function buildOverlayPageHtml({
  width,
  height,
  fontSize,
  padding,
  textColor,
  bgColor,
  fontFamily,
  align,
  noWordSplit,
  headerDefault,
  boxKey
}) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    :root {
      --overlay-width: ${width};
      --overlay-height: ${height};
      --overlay-font-size: ${fontSize};
      --overlay-padding: ${padding};
      --overlay-text-color: ${textColor};
      --overlay-bg-color: ${bgColor};
      --overlay-font-family: ${fontFamily};
      --overlay-align: ${align};
      --overlay-word-break: ${noWordSplit ? "normal" : "break-word"};
      --overlay-overflow-wrap: ${noWordSplit ? "normal" : "anywhere"};
    }
    body { margin: 0; background: transparent; color: var(--overlay-text-color); font-family: var(--overlay-font-family); }
    #frame {
      width: var(--overlay-width);
      box-sizing: border-box;
    }
    #header {
      min-height: 24px;
      font-size: 14px;
      line-height: 1.2;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      opacity: 0.8;
      padding: 2px 0 6px 0;
      box-sizing: border-box;
    }
    #header:empty {
      display: none;
    }
    #box {
      width: var(--overlay-width);
      height: var(--overlay-height);
      padding: var(--overlay-padding);
      background: var(--overlay-bg-color);
      box-sizing: border-box;
    }
    #text {
      font-size: var(--overlay-font-size);
      line-height: 1.2;
      white-space: pre-wrap;
      text-align: var(--overlay-align);
      word-break: var(--overlay-word-break);
      overflow-wrap: var(--overlay-overflow-wrap);
    }
  </style>
</head>
<body>
  <div id="frame">
    <div id="header"></div>
    <div id="box">
      <div id="text"></div>
    </div>
  </div>
  <script>
    const el = document.getElementById("text");
    const header = document.getElementById("header");
    const headerDefault = ${JSON.stringify(headerDefault)};
    const boxKey = ${JSON.stringify(boxKey)};
    const eventsPath = boxKey && boxKey !== "default" ? ("/events?box=" + encodeURIComponent(boxKey)) : "/events";
    const es = new EventSource(eventsPath);
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data || "{}");
        el.textContent = payload.text || "";
        header.textContent = payload.header || headerDefault || "";
        if (payload.width) document.documentElement.style.setProperty("--overlay-width", payload.width);
        if (payload.height) document.documentElement.style.setProperty("--overlay-height", payload.height);
        if (payload.fontSize) document.documentElement.style.setProperty("--overlay-font-size", payload.fontSize);
        if (payload.padding) document.documentElement.style.setProperty("--overlay-padding", payload.padding);
        if (payload.textColor) document.documentElement.style.setProperty("--overlay-text-color", payload.textColor);
        if (payload.bgColor) document.documentElement.style.setProperty("--overlay-bg-color", payload.bgColor);
        if (payload.fontFamily) document.documentElement.style.setProperty("--overlay-font-family", payload.fontFamily);
        if (payload.align) document.documentElement.style.setProperty("--overlay-align", payload.align);
        if (Object.prototype.hasOwnProperty.call(payload, "noWordSplit")) {
          const noSplit = Boolean(payload.noWordSplit);
          document.documentElement.style.setProperty("--overlay-word-break", noSplit ? "normal" : "break-word");
          document.documentElement.style.setProperty("--overlay-overflow-wrap", noSplit ? "normal" : "anywhere");
        }
      } catch (err) {
        el.textContent = ev.data || "";
      }
    };
  </script>
</body>
</html>`;
}

function buildOverlaySettingsHtml() {
  return `<!doctype html>
<html>
<head><meta charset="utf-8" /><style>
body { font-family: sans-serif; padding: 16px; }
label { display:block; margin-top:8px; font-size:12px; text-transform:uppercase; letter-spacing:0.06em; }
input { width: 360px; padding: 6px; }
</style></head>
<body>
<h3>Overlay Settings</h3>
<p><a href="/caption-box-settings">Try the browser caption-box prototype</a></p>
<p>Adjust values and copy URL into OBS Browser source.</p>
<label>Width</label><input id="width" value="640px" />
<label>Height</label><input id="height" value="140px" />
<label>Font Size</label><input id="fontSize" value="32px" />
<label>Padding</label><input id="padding" value="12px" />
<label>Text Color</label><input id="textColor" value="#ffffff" />
<label>Background</label><input id="bgColor" value="rgba(0,0,0,0.35)" />
<label>Font Family</label><input id="fontFamily" value="sans-serif" />
<label>Align</label><input id="align" value="left" />
<label><input id="noWordSplit" type="checkbox" checked /> No Word Split</label>
<label>Header (default)</label><input id="header" value="" />
<label>Overlay URL</label><input id="url" readonly />
<script>
  const fields = ["width","height","fontSize","padding","textColor","bgColor","fontFamily","align","header"];
  const urlEl = document.getElementById("url");
  const noWordSplitEl = document.getElementById("noWordSplit");
  function update() {
    const params = new URLSearchParams();
    fields.forEach((key) => {
      const val = document.getElementById(key).value;
      if (val) params.set(key, val);
    });
    params.set("noWordSplit", noWordSplitEl.checked ? "true" : "false");
    urlEl.value = "/overlay?" + params.toString();
  }
  fields.forEach((key) => document.getElementById(key).addEventListener("input", update));
  noWordSplitEl.addEventListener("change", update);
  update();
</script>
</body></html>`;
}

function createOverlayServerRuntime({
  http,
  normalizeOverlayBoxKey,
  encodeOverlay,
  overlayPayloadForBox,
  overlayClients,
  getOverlayTestStreamEnabled,
  setOverlayTestStreamEnabled,
  notifyExternalTestStream,
  overlayBasePort,
  setTimeoutFn,
  logError
}) {
  let server = null;
  let port = Number(overlayBasePort || 8790);
  let listenAttempts = 0;

  function coerceEnabled(value) {
    if (typeof value === "string") {
      const token = value.trim().toLowerCase();
      if (token === "false" || token === "0" || token === "off" || token === "no") return false;
      if (token === "true" || token === "1" || token === "on" || token === "yes") return true;
    }
    return Boolean(value);
  }

  function getPort() {
    return port;
  }

  function start() {
    if (server) return;
    server = http.createServer((req, res) => {
      const url = new URL(req.url, `http://127.0.0.1:${port}`);
      if (url.pathname === "/caption-box" || url.pathname === "/caption-box-settings") {
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(url.pathname === "/caption-box" ? buildCaptionBoxHtml() : buildCaptionBoxSettingsHtml());
        return;
      }
      if (url.pathname === "/overlay") {
        const qs = url.searchParams;
        const boxKey = normalizeOverlayBoxKey(qs.get("box"));
        const noWordSplitQ = qs.get("noWordSplit");
        const noWordSplit = noWordSplitQ === null
          ? true
          : ["1", "true", "yes"].includes(String(noWordSplitQ).toLowerCase());
        const html = buildOverlayPageHtml({
          boxKey,
          width: qs.get("width") || "640px",
          height: qs.get("height") || "140px",
          fontSize: qs.get("fontSize") || "32px",
          padding: qs.get("padding") || "12px",
          textColor: qs.get("textColor") || "#ffffff",
          bgColor: qs.get("bgColor") || "rgba(0,0,0,0.35)",
          fontFamily: qs.get("fontFamily") || "sans-serif",
          align: qs.get("align") || "left",
          headerDefault: qs.get("header") || "",
          noWordSplit
        });
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(html);
        return;
      }
      if (url.pathname === "/events") {
        const boxKey = normalizeOverlayBoxKey(url.searchParams.get("box"));
        // eslint-disable-next-line no-console
        console.log(`what_gui: http /events connect box=${boxKey} port=${port}`);
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive"
        });
        res.write(`data: ${encodeOverlay(overlayPayloadForBox(boxKey))}\n\n`);
        overlayClients.set(res, boxKey);
        req.on("close", () => {
          overlayClients.delete(res);
          // eslint-disable-next-line no-console
          console.log(`what_gui: http /events disconnect box=${boxKey} port=${port}`);
        });
        return;
      }
      if (url.pathname === "/test-stream") {
        if (req.method === "GET") {
          // eslint-disable-next-line no-console
          console.log(`what_gui: http /test-stream GET enabled=${getOverlayTestStreamEnabled()}`);
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: true, enabled: getOverlayTestStreamEnabled() }));
          return;
        }
        if (req.method === "POST") {
          let body = "";
          req.on("data", (chunk) => {
            body += chunk.toString();
          });
          req.on("end", () => {
            try {
              const payload = body ? JSON.parse(body) : {};
              const enabled = coerceEnabled(payload && payload.enabled);
              const box = String((payload && payload.box) || "").trim().toLowerCase();
              let lanePayload = null;
              if (box && box !== "default" && box !== "all" && box !== "combined") {
                lanePayload = {
                  enabled,
                  box,
                };
                const passthroughKeys = [
                  "linesLimit",
                  "maxChars",
                  "maxSegments",
                  "widthPx",
                  "paddingPx",
                  "fontUi",
                  "maxLineChars",
                  "noWordSplit",
                  "_debug_box_raw_width",
                  "_debug_box_raw_font",
                  "_debug_box_raw_padding",
                  "_debug_box_raw_max_segments",
                  "_debug_box_raw_max_chars",
                ];
                passthroughKeys.forEach((key) => {
                  if (Object.prototype.hasOwnProperty.call(payload, key)) {
                    lanePayload[key] = payload[key];
                  }
                });
                setOverlayTestStreamEnabled(lanePayload);
              } else {
                setOverlayTestStreamEnabled(enabled);
              }
              // eslint-disable-next-line no-console
              console.log(
                `what_gui: http /test-stream POST body='${body}' enabled=${getOverlayTestStreamEnabled()}`
              );
              if (box && box !== "default" && box !== "all" && box !== "combined") {
                notifyExternalTestStream({
                  ...lanePayload,
                  enabled: getOverlayTestStreamEnabled(),
                });
              } else {
                notifyExternalTestStream(getOverlayTestStreamEnabled());
              }
              res.writeHead(200, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ ok: true, enabled: getOverlayTestStreamEnabled() }));
            } catch (err) {
              // eslint-disable-next-line no-console
              console.log(`what_gui: http /test-stream POST parse_error=${String(err)}`);
              res.writeHead(400, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ ok: false, error: String(err) }));
            }
          });
          return;
        }
        res.writeHead(405, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "method not allowed" }));
        return;
      }
      if (url.pathname === "/overlay-settings") {
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(buildOverlaySettingsHtml());
        return;
      }
      res.writeHead(404);
      res.end("not found");
    });

    server.on("error", (err) => {
      if (err && err.code === "EADDRINUSE") {
        listenAttempts += 1;
        if (listenAttempts > 20) {
          port += 1;
          listenAttempts = 0;
        }
        try {
          server.close();
        } catch (_closeErr) {
          // ignore
        }
        server = null;
        setTimeoutFn(() => start(), 200);
        return;
      }
      logError("overlay server error:", err);
    });
    server.on("listening", () => {
      listenAttempts = 0;
      // eslint-disable-next-line no-console
      console.log(`what_gui: overlay server listening port=${port}`);
    });
    server.listen(port);
  }

  function stop() {
    if (!server) return;
    overlayClients.forEach((_boxKey, res) => {
      try {
        res.end();
      } catch (_err) {
        // ignore
      }
    });
    overlayClients.clear();
    server.close();
    server = null;
  }

  return {
    start,
    stop,
    getPort
  };
}

module.exports = {
  createOverlayServerRuntime
};
