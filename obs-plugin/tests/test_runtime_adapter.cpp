#include "what_overlay/pipeline/runtime_adapter.h"

#include <cassert>

using what_overlay::OverlayConfig;
using what_overlay::layout::HeaderSourceAvailability;
using what_overlay::layout::HeaderSourceRole;
using what_overlay::pipeline::IngestRejectReason;
using what_overlay::pipeline::adapt_client_payload_decision;
using what_overlay::pipeline::adapt_header_activation;
using what_overlay::pipeline::adapt_pending_payload_decision;
using what_overlay::pipeline::adapt_render_geometry;
using what_overlay::pipeline::adapt_transition_decision_for_lines;
using what_overlay::pipeline::adapt_transition_decision_for_text;

int main() {
  {
    const auto d = adapt_client_payload_decision(true, "trace-1", false, "", "");
    assert(!d.accepted);
    assert(d.reason == IngestRejectReason::kPluginTestStreamActive);
  }

  {
    OverlayConfig cfg{};
    cfg.header = "Desktop";
    const auto d = adapt_pending_payload_decision(cfg, "Mic", "", false, false, "");
    assert(!d.accepted);
    assert(d.reason == IngestRejectReason::kEmptyPayload);
    assert(d.effective_header == "Desktop");
  }

  {
    OverlayConfig cfg{};
    cfg.header = "Desktop";
    HeaderSourceAvailability availability{};
    availability.has_header = true;
    const auto a = adapt_header_activation(cfg, "Mic", availability);
    assert(a.active_header == "Desktop");
    assert(a.source_role == HeaderSourceRole::kHeader);
  }

  {
    OverlayConfig cfg{};
    cfg.width_px = 640;
    cfg.height_px = 140;
    cfg.padding_x_px = 6;
    cfg.padding_y_px = 4;
    cfg.outline_enabled = true;
    cfg.outline_thickness_px = 3;
    cfg.font_size_px = 7.05;
    const auto g = adapt_render_geometry(cfg, "Desktop");
    assert(g.top_extra_px == 39);
    assert(g.box_y == 39.0f);
  }

  {
    const auto d = adapt_transition_decision_for_lines(
        {"a", "b", "c"},
        {"b", "c", "d"},
        true,
        true,
        false,
        "roll",
        "roll");
    assert(!d.animate);
  }

  {
    const auto d = adapt_transition_decision_for_text(
        {"a", "b", "c"},
        {"b", "c", "d"},
        true,
        true,
        false,
        "roll");
    assert(d.animate);
    assert(d.strict_roll);
  }

  return 0;
}
