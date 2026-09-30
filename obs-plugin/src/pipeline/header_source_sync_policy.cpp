#include "what_overlay/pipeline/header_source_sync_policy.h"

#include "what_overlay/layout/overlay_label_policy.h"

namespace what_overlay::pipeline {

HeaderSourceSyncDecision compute_header_source_sync_decision(const HeaderSourceSyncInput& input) {
  HeaderSourceSyncDecision out;
  out.normalized_active_header = layout::normalize_label_token(input.active_header);
  out.normalized_current_preview = layout::normalize_label_token(input.current_preview);
  out.has_active_header = !out.normalized_active_header.empty();
  if (!out.has_active_header) {
    out.matches_active_header = true;
    out.should_repair = false;
    return out;
  }
  out.matches_active_header = (out.normalized_active_header == out.normalized_current_preview);
  out.should_repair = !out.matches_active_header;
  return out;
}

}  // namespace what_overlay::pipeline
