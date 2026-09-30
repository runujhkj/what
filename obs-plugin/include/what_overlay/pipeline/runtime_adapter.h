#pragma once

#include "what_overlay/overlay_config.h"
#include "what_overlay/layout/source_render_policy.h"
#include "what_overlay/pipeline/header_activation_policy.h"
#include "what_overlay/pipeline/payload_ingest_policy.h"
#include "what_overlay/pipeline/render_geometry_policy.h"
#include "what_overlay/pipeline/transition_policy.h"

#include <string>
#include <vector>

namespace what_overlay::pipeline {

struct ClientPayloadDecision {
  bool accepted = false;
  IngestRejectReason reason = IngestRejectReason::kNone;
};

ClientPayloadDecision adapt_client_payload_decision(bool plugin_test_stream_enabled,
                                                    const std::string& trace_id,
                                                    bool has_lines,
                                                    const std::string& text,
                                                    const std::string& header);

struct PendingPayloadDecision {
  bool accepted = false;
  IngestRejectReason reason = IngestRejectReason::kNone;
  std::string effective_header;
};

PendingPayloadDecision adapt_pending_payload_decision(const OverlayConfig& config,
                                                      const std::string& current_header,
                                                      const std::string& payload_header,
                                                      bool has_payload_header,
                                                      bool has_lines,
                                                      const std::string& text);

HeaderActivationOutput adapt_header_activation(const OverlayConfig& config,
                                               const std::string& current_header,
                                               const layout::HeaderSourceAvailability& availability,
                                               layout::HeaderSourceMode mode =
                                                   layout::HeaderSourceMode::kStrictHeaderOnly);

RenderGeometry adapt_render_geometry(const OverlayConfig& config,
                                     const std::string& active_header);

TransitionDecision adapt_transition_decision_for_lines(
    const std::vector<std::string>& prev_lines,
    const std::vector<std::string>& next_lines,
    bool has_prev,
    bool visible_changed,
    bool currently_animating,
    const std::string& animation_mode,
    const std::string& transition_hint);

TransitionDecision adapt_transition_decision_for_text(
    const std::vector<std::string>& prev_visible_lines,
    const std::vector<std::string>& next_visible_lines,
    bool has_prev,
    bool visible_changed,
    bool currently_animating,
    const std::string& animation_mode);

}  // namespace what_overlay::pipeline
