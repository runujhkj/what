#include "what_overlay/pipeline/runtime_adapter.h"

namespace what_overlay::pipeline {

ClientPayloadDecision adapt_client_payload_decision(bool plugin_test_stream_enabled,
                                                    const std::string& trace_id,
                                                    bool has_lines,
                                                    const std::string& text,
                                                    const std::string& header) {
  ClientPayloadDecision out;
  out.accepted = should_accept_client_payload(
      plugin_test_stream_enabled,
      trace_id,
      has_lines,
      text,
      header,
      &out.reason);
  return out;
}

PendingPayloadDecision adapt_pending_payload_decision(const OverlayConfig& config,
                                                      const std::string& current_header,
                                                      const std::string& payload_header,
                                                      bool has_payload_header,
                                                      bool has_lines,
                                                      const std::string& text) {
  PendingPayloadDecision out;
  out.effective_header = resolve_effective_header_for_pending(
      payload_header,
      has_payload_header,
      config.header,
      current_header);
  out.accepted = should_accept_pending_payload(
      has_lines,
      text,
      payload_header,
      &out.reason);
  return out;
}

HeaderActivationOutput adapt_header_activation(const OverlayConfig& config,
                                               const std::string& current_header,
                                               const layout::HeaderSourceAvailability& availability,
                                               layout::HeaderSourceMode mode) {
  HeaderActivationInput in{};
  in.configured_header = config.header;
  in.current_header = current_header;
  in.source_availability = availability;
  in.source_mode = mode;
  return compute_header_activation(in);
}

RenderGeometry adapt_render_geometry(const OverlayConfig& config,
                                     const std::string& active_header) {
  RenderGeometryInput in{};
  in.width_px = config.width_px;
  in.height_px = config.height_px;
  in.padding_x_px = config.padding_x_px;
  in.padding_y_px = config.padding_y_px;
  in.outline_enabled = config.outline_enabled;
  in.outline_thickness_px = config.outline_thickness_px;
  in.font_size_px = config.font_size_px;
  in.active_header = active_header;
  return compute_render_geometry(in);
}

TransitionDecision adapt_transition_decision_for_lines(
    const std::vector<std::string>& prev_lines,
    const std::vector<std::string>& next_lines,
    bool has_prev,
    bool visible_changed,
    bool currently_animating,
    const std::string& animation_mode,
    const std::string& transition_hint) {
  const TransitionLineRelationship relation = compute_line_relationship(prev_lines, next_lines);
  TransitionDecisionInput input{};
  input.has_prev = has_prev;
  input.visible_changed = visible_changed;
  input.currently_animating = currently_animating;
  input.animation_mode = animation_mode;
  input.transition_hint = transition_hint;
  input.strict_roll = relation.strict_roll;
  input.grow_append = relation.grow_append;
  input.allow_transition_hints = true;
  input.disable_animation = true;
  return decide_transition(input);
}

TransitionDecision adapt_transition_decision_for_text(
    const std::vector<std::string>& prev_visible_lines,
    const std::vector<std::string>& next_visible_lines,
    bool has_prev,
    bool visible_changed,
    bool currently_animating,
    const std::string& animation_mode) {
  const TransitionLineRelationship relation = compute_line_relationship(prev_visible_lines, next_visible_lines);
  TransitionDecisionInput input{};
  input.has_prev = has_prev;
  input.visible_changed = visible_changed;
  input.currently_animating = currently_animating;
  input.animation_mode = animation_mode;
  input.strict_roll = relation.strict_roll;
  input.grow_append = relation.grow_append;
  return decide_transition(input);
}

}  // namespace what_overlay::pipeline
