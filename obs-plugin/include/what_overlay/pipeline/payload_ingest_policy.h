#pragma once

#include <string>

namespace what_overlay::pipeline {

enum class IngestRejectReason {
  kNone = 0,
  kPluginTestStreamActive = 1,
  kEmptyHeartbeat = 2,
  kEmptyPayload = 3,
};

// Per-source caption-stream filter. A source with a non-empty `filter` renders only
// payloads whose input_source_id (or, as a fallback, client_id) equals it; an empty filter
// renders all streams. Lets two sources give independent mic/desktop caption boxes.
bool payload_stream_matches(const std::string& input_source_id,
                            const std::string& client_id,
                            const std::string& filter);

bool should_accept_client_payload(bool plugin_test_stream_enabled,
                                  const std::string& trace_id,
                                  bool has_lines,
                                  const std::string& text,
                                  const std::string& header,
                                  IngestRejectReason* reason = nullptr);

bool should_accept_pending_payload(bool has_lines,
                                   const std::string& text,
                                   const std::string& payload_header,
                                   IngestRejectReason* reason = nullptr);

std::string resolve_effective_header_for_pending(const std::string& payload_header,
                                                 bool has_payload_header,
                                                 const std::string& configured_header,
                                                 const std::string& current_header);

const char* reject_reason_cstr(IngestRejectReason reason);

}  // namespace what_overlay::pipeline
