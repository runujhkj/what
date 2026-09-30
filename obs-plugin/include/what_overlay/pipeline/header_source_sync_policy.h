#pragma once

#include <string>

namespace what_overlay::pipeline {

struct HeaderSourceSyncInput {
  std::string active_header;
  std::string current_preview;
};

struct HeaderSourceSyncDecision {
  bool has_active_header = false;
  bool matches_active_header = false;
  bool should_repair = false;
  std::string normalized_active_header;
  std::string normalized_current_preview;
};

HeaderSourceSyncDecision compute_header_source_sync_decision(const HeaderSourceSyncInput& input);

}  // namespace what_overlay::pipeline
