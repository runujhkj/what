#include "what_overlay/overlay_state.h"

#include <algorithm>
#include <mutex>

namespace what_overlay {
namespace {

struct OverlayStateStore {
  std::mutex mutex;
  OverlayStateSnapshot snapshot;
};

OverlayStateStore& state_store() {
  static OverlayStateStore store;
  return store;
}

uint64_t bump_version_locked(OverlayStateStore& store) {
  store.snapshot.version += 1;
  return store.snapshot.version;
}

}  // namespace

OverlayStateSnapshot overlay_state_snapshot() {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  return store.snapshot;
}

uint64_t overlay_state_set_config(const OverlayConfig& config) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  store.snapshot.config = config;
  return bump_version_locked(store);
}

uint64_t overlay_state_set_geometry(int width_px, int height_px, int pad_x_px, int pad_y_px) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  const int new_w = std::max(100, width_px);
  const int new_h = std::max(60, height_px);
  const int max_pad_x = std::max(0, (new_w / 2) - 1);
  const int max_pad_y = std::max(0, (new_h / 2) - 1);
  const int new_pad_x = std::max(0, std::min(pad_x_px, max_pad_x));
  const int new_pad_y = std::max(0, std::min(pad_y_px, max_pad_y));

  if (store.snapshot.config.width_px == new_w &&
      store.snapshot.config.height_px == new_h &&
      store.snapshot.config.padding_x_px == new_pad_x &&
      store.snapshot.config.padding_y_px == new_pad_y) {
    return store.snapshot.version;
  }

  store.snapshot.config.width_px = new_w;
  store.snapshot.config.height_px = new_h;
  store.snapshot.config.padding_x_px = new_pad_x;
  store.snapshot.config.padding_y_px = new_pad_y;
  return bump_version_locked(store);
}

uint64_t overlay_state_set_delay_seconds(int delay_seconds) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  store.snapshot.config.delay_seconds = std::max(0, std::min(90, delay_seconds));
  return bump_version_locked(store);
}

uint64_t overlay_state_set_delay_readback(const std::string& delay_readback) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  store.snapshot.delay_readback = delay_readback;
  return bump_version_locked(store);
}

uint64_t overlay_state_set_rendered_text(const std::string& rendered_text) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  store.snapshot.rendered_text = rendered_text;
  store.snapshot.rendered_segment_ids.clear();
  store.snapshot.rendered_segments.clear();
  store.snapshot.rendered_spans.clear();
  return bump_version_locked(store);
}

uint64_t overlay_state_set_rendered_output(
    const std::string& rendered_text,
    const std::vector<std::string>& rendered_segment_ids,
    const std::vector<std::string>& rendered_segments,
    const std::vector<OverlayRenderedSpan>& rendered_spans) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  store.snapshot.rendered_text = rendered_text;
  store.snapshot.rendered_segment_ids = rendered_segment_ids;
  store.snapshot.rendered_segments = rendered_segments;
  store.snapshot.rendered_spans = rendered_spans;
  return bump_version_locked(store);
}

uint64_t overlay_state_set_effective_font_size(double effective_font_size_px) {
  auto& store = state_store();
  std::lock_guard<std::mutex> lock(store.mutex);
  store.snapshot.effective_font_size_px = std::max(0.1, effective_font_size_px);
  return bump_version_locked(store);
}

}  // namespace what_overlay
