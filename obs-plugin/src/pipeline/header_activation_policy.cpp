#include "what_overlay/pipeline/header_activation_policy.h"

#include "what_overlay/layout/overlay_label_policy.h"

namespace what_overlay::pipeline {

HeaderActivationOutput compute_header_activation(const HeaderActivationInput& input) {
  HeaderActivationOutput out;
  out.active_header = layout::select_active_header(input.configured_header, input.current_header);
  out.has_active_header = !layout::normalize_label_token(out.active_header).empty();
  out.source_role = layout::select_header_source_role(input.source_availability, input.source_mode);
  return out;
}

std::string resolve_header_update_text(const std::string& configured_header,
                                       const std::string& requested_header) {
  return layout::select_active_header(configured_header, requested_header);
}

}  // namespace what_overlay::pipeline
