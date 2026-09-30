#include "what_overlay/layout/source_render_policy.h"

#include <cassert>

using what_overlay::layout::HeaderSourceAvailability;
using what_overlay::layout::HeaderSourceMode;
using what_overlay::layout::HeaderSourceRole;
using what_overlay::layout::select_header_source_role;

int main() {
  {
    HeaderSourceAvailability a{};
    assert(select_header_source_role(a) == HeaderSourceRole::kNone);
  }
  {
    HeaderSourceAvailability a{};
    a.has_prev = true;
    assert(select_header_source_role(a) == HeaderSourceRole::kNone);
  }
  {
    HeaderSourceAvailability a{};
    a.has_prev = true;
    a.has_header = true;
    assert(select_header_source_role(a) == HeaderSourceRole::kHeader);
  }
  {
    HeaderSourceAvailability a{};
    a.has_prev = true;
    assert(select_header_source_role(a, HeaderSourceMode::kCompatFallback) == HeaderSourceRole::kPrev);
  }
  {
    HeaderSourceAvailability a{};
    a.has_prev = true;
    a.has_header = true;
    a.has_enter = true;
    assert(select_header_source_role(a) == HeaderSourceRole::kHeader);
    assert(select_header_source_role(a, HeaderSourceMode::kCompatFallback) == HeaderSourceRole::kEnter);
  }
  {
    HeaderSourceAvailability a{};
    a.has_prev = true;
    a.has_header = true;
    a.has_enter = true;
    a.has_overflow = true;
    assert(select_header_source_role(a) == HeaderSourceRole::kHeader);
    assert(select_header_source_role(a, HeaderSourceMode::kCompatFallback) == HeaderSourceRole::kOverflow);
  }
  return 0;
}
