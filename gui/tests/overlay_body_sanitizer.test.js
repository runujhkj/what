const assert = require("assert");
const sanitizer = require("../lib/overlay_body_sanitizer");

function testNormalizeLabelToken() {
  assert.strictEqual(sanitizer.normalizeLabelToken(" Mic: "), "mic");
  assert.strictEqual(sanitizer.normalizeLabelToken("Desktop"), "desktop");
  assert.strictEqual(sanitizer.normalizeLabelToken(""), "");
}

function testStripLabelPrefixFromLine() {
  const labels = ["Mic", "Desktop"];
  assert.strictEqual(sanitizer.stripLabelPrefixFromLine("Mic: hello", labels), "hello");
  assert.strictEqual(sanitizer.stripLabelPrefixFromLine("Desktop - world", labels), "world");
  assert.strictEqual(sanitizer.stripLabelPrefixFromLine("Desktop hello", labels), "hello");
  assert.strictEqual(sanitizer.stripLabelPrefixFromLine("NoLabel text", labels), "NoLabel text");
}

function testSanitizeBodyRemovesLabelOnlyLines() {
  const out = sanitizer.sanitizeBody(["Mic", "hello there", "Desktop"], "", ["Mic", "Desktop"]);
  assert.deepStrictEqual(out.lines, ["hello there"]);
  assert.strictEqual(out.text, "hello there");
}

function testSanitizeBodyRemovesLabelPrefixes() {
  const out = sanitizer.sanitizeBody(
    ["Mic: one two", "Desktop | three four", "Desktop five six", "plain five"],
    "",
    ["Mic", "Desktop"]
  );
  assert.deepStrictEqual(out.lines, ["one two", "three four", "five six", "plain five"]);
  assert.strictEqual(out.text, "one two\nthree four\nfive six\nplain five");
}

function testSanitizeBodyFromTextWhenLinesMissing() {
  const out = sanitizer.sanitizeBody(
    null,
    "Mic\nMic: alpha\nDesktop - beta\nplain",
    ["Mic", "Desktop"]
  );
  assert.deepStrictEqual(out.lines, ["alpha", "beta", "plain"]);
  assert.strictEqual(out.text, "alpha\nbeta\nplain");
}

function testSanitizeBodyDoesNotStripNonLabelWords() {
  const out = sanitizer.sanitizeBody(
    ["microphone check", "desktoping is not a label", "microscope test"],
    "",
    ["Mic", "Desktop"]
  );
  assert.deepStrictEqual(out.lines, ["microphone check", "desktoping is not a label", "microscope test"]);
}

testNormalizeLabelToken();
testStripLabelPrefixFromLine();
testSanitizeBodyRemovesLabelOnlyLines();
testSanitizeBodyRemovesLabelPrefixes();
testSanitizeBodyFromTextWhenLinesMissing();
testSanitizeBodyDoesNotStripNonLabelWords();
console.log("overlay_body_sanitizer.test.js: ok");
