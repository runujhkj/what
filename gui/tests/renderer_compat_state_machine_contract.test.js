const assert = require("assert");

function selectCompatSegmentsWindow(allSegments, maxSeg, modeOverride, compatWindowMode) {
  const mode = modeOverride || (compatWindowMode && compatWindowMode.value ? compatWindowMode.value : "paged");
  const pageSize = Math.max(1, maxSeg);
  if (!Array.isArray(allSegments) || allSegments.length === 0) return [];
  if (mode === "lined") return allSegments.slice(-pageSize);
  if (mode === "rolling") return allSegments.slice(-pageSize);
  const pageIndex = Math.floor((allSegments.length - 1) / pageSize);
  const start = pageIndex * pageSize;
  return allSegments.slice(start, start + pageSize);
}

function currentCompatPreviewTab(compatPreviewTab) {
  const tab = String(compatPreviewTab && compatPreviewTab.value ? compatPreviewTab.value : "combined").toLowerCase();
  if (tab === "mic" || tab === "desktop") return tab;
  return "combined";
}

function testCompatWindowModes() {
  const segments = ["s1", "s2", "s3", "s4", "s5"];
  assert.deepStrictEqual(
    selectCompatSegmentsWindow(segments, 2, "paged", { value: "paged" }),
    ["s5"]
  );
  assert.deepStrictEqual(
    selectCompatSegmentsWindow(segments, 2, "rolling", { value: "paged" }),
    ["s4", "s5"]
  );
  assert.deepStrictEqual(
    selectCompatSegmentsWindow(segments, 3, "lined", { value: "paged" }),
    ["s3", "s4", "s5"]
  );
}

function testCompatPreviewTabNormalization() {
  assert.strictEqual(currentCompatPreviewTab({ value: "combined" }), "combined");
  assert.strictEqual(currentCompatPreviewTab({ value: "mic" }), "mic");
  assert.strictEqual(currentCompatPreviewTab({ value: "desktop" }), "desktop");
  assert.strictEqual(currentCompatPreviewTab({ value: "weird" }), "combined");
  assert.strictEqual(currentCompatPreviewTab(null), "combined");
}

testCompatWindowModes();
testCompatPreviewTabNormalization();
console.log("renderer_compat_state_machine_contract.test.js: ok");
