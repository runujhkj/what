#include "what_overlay/layout/source_render_policy.h"

namespace what_overlay::layout {

HeaderSourceRole select_header_source_role(const HeaderSourceAvailability& availability,
                                           HeaderSourceMode mode) {
  if (mode == HeaderSourceMode::kStrictHeaderOnly) {
    return availability.has_header ? HeaderSourceRole::kHeader : HeaderSourceRole::kNone;
  }
  if (availability.has_overflow) return HeaderSourceRole::kOverflow;
  if (availability.has_enter) return HeaderSourceRole::kEnter;
  if (availability.has_header) return HeaderSourceRole::kHeader;
  if (availability.has_prev) return HeaderSourceRole::kPrev;
  return HeaderSourceRole::kNone;
}

}  // namespace what_overlay::layout
