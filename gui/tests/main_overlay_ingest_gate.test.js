const assert = require("assert");
const gate = require("../lib/main_overlay_ingest_gate");

function testIgnoredWhenPolicyRejects() {
  let stored = null;
  const logs = [];
  const ingestOverlayPayload = gate.createOverlayIngestGate({
    shouldAcceptIncomingOverlayPayload: () => ({ accept: false, reason: "non_test_payload_while_test_stream_on" }),
    isLocalTestStreamEnabled: () => true,
    setOverlayPayload: (next) => { stored = next; },
    log: (line) => logs.push(line),
  });

  const out = ingestOverlayPayload({ trace_id: "external-42", lines: ["hello"] });
  assert.deepStrictEqual(out, { accepted: false, reason: "non_test_payload_while_test_stream_on" });
  assert.strictEqual(stored, null);
  assert.ok(logs[0].includes("set-overlay-text ignored while local-test-stream enabled"));
  assert.ok(logs[0].includes("trace='external-42'"));
}

function testAcceptedWhenPolicyAccepts() {
  let stored = null;
  const logs = [];
  const ingestOverlayPayload = gate.createOverlayIngestGate({
    shouldAcceptIncomingOverlayPayload: () => ({ accept: true, reason: "local_test_payload" }),
    isLocalTestStreamEnabled: () => false,
    setOverlayPayload: (next) => { stored = next; },
    log: (line) => logs.push(line),
  });

  const payload = { trace_id: "main-test-4", lines: ["test segment 4"] };
  const out = ingestOverlayPayload(payload);
  assert.deepStrictEqual(out, { accepted: true, reason: "local_test_payload" });
  assert.deepStrictEqual(stored, payload);
  assert.ok(logs[0].includes("set-overlay-text accepted while test_stream=off"));
}

function run() {
  testIgnoredWhenPolicyRejects();
  testAcceptedWhenPolicyAccepts();
  console.log("main_overlay_ingest_gate.test.js: ok");
}

run();
