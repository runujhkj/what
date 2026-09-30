#pragma once

#include "what_overlay/layout/source_render_policy.h"

#include <string>

namespace what_overlay::pipeline {

struct HeaderActivationInput {
  std::string configured_header;
  std::string current_header;
  layout::HeaderSourceAvailability source_availability{};
  layout::HeaderSourceMode source_mode = layout::HeaderSourceMode::kStrictHeaderOnly;
};

struct HeaderActivationOutput {
  std::string active_header;
  layout::HeaderSourceRole source_role = layout::HeaderSourceRole::kNone;
  bool has_active_header = false;
};

HeaderActivationOutput compute_header_activation(const HeaderActivationInput& input);

std::string resolve_header_update_text(const std::string& configured_header,
                                       const std::string& requested_header);

}  // namespace what_overlay::pipeline
