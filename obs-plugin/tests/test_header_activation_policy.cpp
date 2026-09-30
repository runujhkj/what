#include "what_overlay/pipeline/header_activation_policy.h"

#include <cassert>

using what_overlay::layout::HeaderSourceAvailability;
using what_overlay::layout::HeaderSourceMode;
using what_overlay::layout::HeaderSourceRole;
using what_overlay::pipeline::HeaderActivationInput;
using what_overlay::pipeline::compute_header_activation;
using what_overlay::pipeline::resolve_header_update_text;

int main() {
  {
    HeaderActivationInput in{};
    in.configured_header = "Desktop";
    in.current_header = "Mic";
    in.source_availability.has_header = true;
    const auto out = compute_header_activation(in);
    assert(out.active_header == "Desktop");
    assert(out.has_active_header);
    assert(out.source_role == HeaderSourceRole::kHeader);
  }

  {
    HeaderActivationInput in{};
    in.current_header = "Mic";
    in.source_availability.has_prev = true;
    const auto out = compute_header_activation(in);
    assert(out.active_header == "Mic");
    assert(out.has_active_header);
    assert(out.source_role == HeaderSourceRole::kNone);
  }

  {
    HeaderActivationInput in{};
    in.current_header = "Mic";
    in.source_mode = HeaderSourceMode::kCompatFallback;
    in.source_availability.has_prev = true;
    const auto out = compute_header_activation(in);
    assert(out.source_role == HeaderSourceRole::kPrev);
  }

  {
    assert(resolve_header_update_text("Desktop", "") == "Desktop");
    assert(resolve_header_update_text("", "Mic") == "Mic");
    assert(resolve_header_update_text("", "") == "");
  }

  return 0;
}
