#pragma once

namespace what_overlay::layout {

enum class HeaderSourceRole {
  kNone = 0,
  kOverflow = 1,
  kEnter = 2,
  kHeader = 3,
  kPrev = 4,
};

enum class HeaderSourceMode {
  // Isolate header rendering to the dedicated header source only.
  kStrictHeaderOnly = 0,
  // Legacy fallback order used while migrating older behavior.
  kCompatFallback = 1,
};

struct HeaderSourceAvailability {
  bool has_overflow = false;
  bool has_enter = false;
  bool has_header = false;
  bool has_prev = false;
};

HeaderSourceRole select_header_source_role(
    const HeaderSourceAvailability& availability,
    HeaderSourceMode mode = HeaderSourceMode::kStrictHeaderOnly);

}  // namespace what_overlay::layout
