(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.whatGuiOverlayLabelPolicy = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function normalizeLabelToken(value) {
    return String(value || "")
      .trim()
      .replace(/[:\-\u2013\u2014]\s*$/, "")
      .toLowerCase();
  }

  function canonicalLabelSet(input) {
    const items = Array.isArray(input) ? input : [input];
    const out = new Set();
    items.forEach((v) => {
      const normalized = normalizeLabelToken(v);
      if (normalized) out.add(normalized);
    });
    return out;
  }

  function isLabelOnlyLine(line, labels) {
    const normalized = normalizeLabelToken(line);
    return normalized ? labels.has(normalized) : false;
  }

  function escapeRegex(source) {
    return String(source || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function stripLeadingLabel(line, labelsIn) {
    let out = String(line || "");
    const labels = labelsIn instanceof Set ? labelsIn : canonicalLabelSet(labelsIn);
    labels.forEach((label) => {
      const escaped = escapeRegex(label);
      const re = new RegExp(
        "^\\s*" + escaped + "(?:\\s*[:\\-\\u2013\\u2014\\|]\\s*|\\s+)",
        "i"
      );
      out = out.replace(re, "");
    });
    return out.trim();
  }

  function sanitizeBodyLines(linesIn, labelCandidates) {
    const labels = canonicalLabelSet(labelCandidates);
    const src = Array.isArray(linesIn) ? linesIn : [String(linesIn || "")];
    const out = [];

    for (const rawLine of src) {
      const raw = String(rawLine || "");
      if (!raw.trim()) continue;
      if (isLabelOnlyLine(raw, labels)) continue;
      const stripped = stripLeadingLabel(raw, labels);
      if (stripped && !isLabelOnlyLine(stripped, labels)) out.push(stripped);
    }
    return out;
  }

  return {
    normalizeLabelToken,
    canonicalLabelSet,
    isLabelOnlyLine,
    stripLeadingLabel,
    sanitizeBodyLines,
  };
});
