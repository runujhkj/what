#include "what_overlay/pipeline/payload_ingest_policy.h"

#include "what_overlay/layout/overlay_label_policy.h"

namespace what_overlay::pipeline {

namespace {

bool is_main_test_trace_id(const std::string& trace_id) {
  return !trace_id.empty() && trace_id.rfind("main-test-", 0) == 0;
}

}  // namespace

bool payload_stream_matches(const std::string& input_source_id,
                            const std::string& client_id,
                            const std::string& filter) {
  if (filter.empty()) return true;
  const std::string& src = !input_source_id.empty() ? input_source_id : client_id;
  return src == filter;
}

bool should_accept_client_payload(bool plugin_test_stream_enabled,
                                  const std::string& trace_id,
                                  bool has_lines,
                                  const std::string& text,
                                  const std::string& header,
                                  IngestRejectReason* reason) {
  if (plugin_test_stream_enabled && !is_main_test_trace_id(trace_id)) {
    if (reason) *reason = IngestRejectReason::kPluginTestStreamActive;
    return false;
  }
  if (!has_lines && text.empty() && header.empty()) {
    if (reason) *reason = IngestRejectReason::kEmptyHeartbeat;
    return false;
  }
  if (reason) *reason = IngestRejectReason::kNone;
  return true;
}

bool should_accept_pending_payload(bool has_lines,
                                   const std::string& text,
                                   const std::string& payload_header,
                                   IngestRejectReason* reason) {
  const std::string payload_header_norm = what_overlay::layout::normalize_label_token(payload_header);
  if (!has_lines && text.empty() && payload_header_norm.empty()) {
    if (reason) *reason = IngestRejectReason::kEmptyPayload;
    return false;
  }
  if (reason) *reason = IngestRejectReason::kNone;
  return true;
}

std::string resolve_effective_header_for_pending(const std::string& payload_header,
                                                 bool has_payload_header,
                                                 const std::string& configured_header,
                                                 const std::string& current_header) {
  const std::string payload_header_norm = what_overlay::layout::normalize_label_token(payload_header);
  const std::string config_header_norm = what_overlay::layout::normalize_label_token(configured_header);
  if (!config_header_norm.empty()) return configured_header;
  if (has_payload_header && !payload_header_norm.empty()) return payload_header;
  return current_header.empty() ? std::string{} : current_header;
}

const char* reject_reason_cstr(IngestRejectReason reason) {
  switch (reason) {
    case IngestRejectReason::kPluginTestStreamActive:
      return "plugin_test_stream_active";
    case IngestRejectReason::kEmptyHeartbeat:
      return "empty_heartbeat";
    case IngestRejectReason::kEmptyPayload:
      return "empty_payload";
    case IngestRejectReason::kNone:
    default:
      return "none";
  }
}

}  // namespace what_overlay::pipeline
