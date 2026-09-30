(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("./overlay_label_policy"));
    return;
  }
  const labelPolicy = root.whatGuiOverlayLabelPolicy || {};
  root.whatGuiOverlayBodySanitizer = factory(labelPolicy);
})(typeof globalThis !== "undefined" ? globalThis : this, function (labelPolicy) {
  const normalizeLabelToken =
    labelPolicy && typeof labelPolicy.normalizeLabelToken === "function"
      ? labelPolicy.normalizeLabelToken
      : function fallbackNormalizeLabelToken(value) {
          let s = String(value || "").trim().toLowerCase();
          if (s.endsWith(":")) s = s.slice(0, -1).trim();
          return s;
        };

  const canonicalLabelSet =
    labelPolicy && typeof labelPolicy.canonicalLabelSet === "function"
      ? labelPolicy.canonicalLabelSet
      : function fallbackCanonicalLabelSet(input) {
          const items = Array.isArray(input) ? input : [input];
          const out = new Set();
          items.forEach((v) => {
            const n = normalizeLabelToken(v);
            if (n) out.add(n);
          });
          return out;
        };

  const stripLeadingLabel =
    labelPolicy && typeof labelPolicy.stripLeadingLabel === "function"
      ? labelPolicy.stripLeadingLabel
      : function fallbackStripLeadingLabel(line, labelsIn) {
          let out = String(line || "");
          const labels = labelsIn instanceof Set ? labelsIn : canonicalLabelSet(labelsIn);
          labels.forEach((label) => {
            const escaped = String(label || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            const re = new RegExp("^\\s*" + escaped + "(?:\\s*[:\\-\\u2013\\u2014\\|]\\s*|\\s+)", "i");
            out = out.replace(re, "");
          });
          return out.trim();
        };

  function sanitizeBody(linesIn, textIn, labelsIn) {
    const labels = canonicalLabelSet(labelsIn);
    const srcLines = Array.isArray(linesIn)
      ? linesIn.map((v) => String(v || ""))
      : String(textIn || "").split("\n").map((v) => String(v || ""));
    const outLines = [];
    for (const raw of srcLines) {
      if (!raw.trim()) continue;
      const normalized = normalizeLabelToken(raw);
      if (normalized && labels.has(normalized)) continue;
      const stripped = stripLeadingLabel(raw, labels);
      if (stripped) outLines.push(stripped);
    }
    return {
      lines: outLines,
      text: outLines.join("\n").trim(),
    };
  }

  function stripLabelPrefixFromLine(line, labels) {
    return stripLeadingLabel(line, labels);
  }

  return {
    normalizeLabelToken,
    stripLabelPrefixFromLine,
    sanitizeBody,
  };
});
