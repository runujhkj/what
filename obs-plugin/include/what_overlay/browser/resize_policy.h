#pragma once
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>

namespace what_overlay::browser {
struct Viewport { int width; int height; };

// Observe a gesture before acting: loading an already-scaled scene is not a drag.
// Wait for a short pause so OBS's mouse-drag origin is not rewritten every frame.
class ResizePolicy {
 public:
  void reset() { key_.clear(); pending_ = false; }
  std::optional<Viewport> observe(const std::string& key, int width, int height,
                                  double sx, double sy, bool eligible, double seconds) {
    if (!eligible || !std::isfinite(sx) || !std::isfinite(sy) || sx <= 0 || sy <= 0) {
      reset();
      return {};
    }
    if (key != key_ || width != width_ || height != height_) {
      key_ = key; width_ = width; height_ = height;
      sx_ = sx; sy_ = sy; pending_ = false;
      return {};
    }
    if (std::abs(sx - sx_) * width > 0.5 || std::abs(sy - sy_) * height > 0.5) {
      sx_ = sx; sy_ = sy; quiet_ = 0; pending_ = true;
      return {};
    }
    if (!pending_) return {};
    quiet_ += seconds;
    if (quiet_ < 0.20) return {};
    pending_ = false;
    if (std::abs(width * sx - width) < 1 && std::abs(height * sy - height) < 1) return {};
    return Viewport{static_cast<int>(std::round(std::clamp(width * sx, 80.0, 4096.0))),
                    static_cast<int>(std::round(std::clamp(height * sy, 60.0, 4096.0)))};
  }
 private:
  std::string key_;
  int width_ = 0, height_ = 0;
  double sx_ = 1, sy_ = 1, quiet_ = 0;
  bool pending_ = false;
};
} // namespace what_overlay::browser
