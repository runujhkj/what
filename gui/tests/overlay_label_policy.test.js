const assert = require("assert");
const policy = require("../lib/overlay_label_policy");

function testNormalizeLabelToken() {
  assert.strictEqual(policy.normalizeLabelToken(" Mic: "), "mic");
  assert.strictEqual(policy.normalizeLabelToken("Desktop"), "desktop");
  assert.strictEqual(policy.normalizeLabelToken(""), "");
}

function testCanonicalLabelSet() {
  const set = policy.canonicalLabelSet([" Mic ", "desktop:", ""]);
  assert.ok(set instanceof Set);
  assert.deepStrictEqual(Array.from(set).sort(), ["desktop", "mic"]);
}

function testStripLeadingLabel() {
  const labels = policy.canonicalLabelSet(["Mic", "Desktop"]);
  assert.strictEqual(policy.stripLeadingLabel("Mic: hello", labels), "hello");
  assert.strictEqual(policy.stripLeadingLabel("Desktop - world", labels), "world");
  assert.strictEqual(policy.stripLeadingLabel("desktop hello", labels), "hello");
  assert.strictEqual(policy.stripLeadingLabel("NoLabel text", labels), "NoLabel text");
}

function testSanitizeBodyLines() {
  const out = policy.sanitizeBodyLines(
    ["Mic", "Desktop", "Desktop: one", "desktop two", "plain"],
    ["Mic", "Desktop"]
  );
  assert.deepStrictEqual(out, ["one", "two", "plain"]);
}

testNormalizeLabelToken();
testCanonicalLabelSet();
testStripLeadingLabel();
testSanitizeBodyLines();
console.log("overlay_label_policy.test.js: ok");
