#include "what_overlay/pipeline/header_source_sync_policy.h"

#include <cassert>

using what_overlay::pipeline::HeaderSourceSyncInput;
using what_overlay::pipeline::compute_header_source_sync_decision;

int main() {
  {
    const auto d = compute_header_source_sync_decision(HeaderSourceSyncInput{"", "Desktop"});
    assert(!d.has_active_header);
    assert(d.matches_active_header);
    assert(!d.should_repair);
  }

  {
    const auto d = compute_header_source_sync_decision(HeaderSourceSyncInput{"Desktop", "desktop"});
    assert(d.has_active_header);
    assert(d.matches_active_header);
    assert(!d.should_repair);
  }

  {
    const auto d = compute_header_source_sync_decision(HeaderSourceSyncInput{"Mic", ""});
    assert(d.has_active_header);
    assert(!d.matches_active_header);
    assert(d.should_repair);
  }

  {
    const auto d = compute_header_source_sync_decision(HeaderSourceSyncInput{"Desktop", "Mic"});
    assert(d.has_active_header);
    assert(!d.matches_active_header);
    assert(d.should_repair);
  }

  return 0;
}
