#include "what_overlay/pipeline/payload_ingest_policy.h"

#include <cassert>
#include <string>

using what_overlay::pipeline::IngestRejectReason;
using what_overlay::pipeline::reject_reason_cstr;
using what_overlay::pipeline::resolve_effective_header_for_pending;
using what_overlay::pipeline::should_accept_client_payload;
using what_overlay::pipeline::should_accept_pending_payload;

int main() {
  {
    IngestRejectReason reason = IngestRejectReason::kNone;
    const bool ok = should_accept_client_payload(
        true,
        "trace-123",
        false,
        "",
        "",
        &reason);
    assert(!ok);
    assert(reason == IngestRejectReason::kPluginTestStreamActive);
    assert(std::string(reject_reason_cstr(reason)) == "plugin_test_stream_active");
  }

  {
    IngestRejectReason reason = IngestRejectReason::kNone;
    const bool ok = should_accept_client_payload(
        true,
        "main-test-abc",
        false,
        "",
        "",
        &reason);
    assert(!ok);
    assert(reason == IngestRejectReason::kEmptyHeartbeat);
  }

  {
    IngestRejectReason reason = IngestRejectReason::kNone;
    const bool ok = should_accept_client_payload(
        false,
        "trace-456",
        true,
        "",
        "",
        &reason);
    assert(ok);
    assert(reason == IngestRejectReason::kNone);
  }

  {
    IngestRejectReason reason = IngestRejectReason::kNone;
    const bool ok = should_accept_pending_payload(false, "", "", &reason);
    assert(!ok);
    assert(reason == IngestRejectReason::kEmptyPayload);
  }

  {
    IngestRejectReason reason = IngestRejectReason::kNone;
    const bool ok = should_accept_pending_payload(false, "", "Desktop", &reason);
    assert(ok);
    assert(reason == IngestRejectReason::kNone);
  }

  {
    const std::string effective = resolve_effective_header_for_pending(
        "Payload",
        true,
        "Configured",
        "Current");
    assert(effective == "Configured");
  }

  {
    const std::string effective = resolve_effective_header_for_pending(
        "Payload",
        true,
        "",
        "Current");
    assert(effective == "Payload");
  }

  {
    const std::string effective = resolve_effective_header_for_pending(
        "",
        false,
        "",
        "Current");
    assert(effective == "Current");
  }

  // Per-source caption-stream filter.
  {
    using what_overlay::pipeline::payload_stream_matches;
    // Empty filter renders everything.
    assert(payload_stream_matches("mic", "other-app", ""));
    assert(payload_stream_matches("desktop", "desktop-helper-session", ""));
    // input_source_id match / mismatch.
    assert(payload_stream_matches("mic", "other-app", "mic"));
    assert(!payload_stream_matches("desktop", "desktop-helper-session", "mic"));
    assert(payload_stream_matches("desktop", "desktop-helper-session", "desktop"));
    // Fallback to client_id when input_source_id is absent.
    assert(payload_stream_matches("", "desktop-helper-session", "desktop-helper-session"));
    assert(!payload_stream_matches("", "other-app", "desktop"));
  }

  return 0;
}
