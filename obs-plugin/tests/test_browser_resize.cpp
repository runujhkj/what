#include "what_overlay/browser/resize_policy.h"
#include <cassert>
#include <limits>
using what_overlay::browser::ResizePolicy;
int main() {
  ResizePolicy policy;
  auto observe = [&](double x, double y, double dt = 0.1, bool eligible = true) {
    return policy.observe("scene:1", 640, 240, x, y, eligible, dt);
  };
  // Existing transforms are baselines, not implicit resize commands.
  assert(!observe(2, 2));
  assert(!observe(2, 2, 1));
  assert(!observe(1.5, 0.5));
  assert(!observe(1.5, 0.5));
  auto target = observe(1.5, 0.5);
  assert(target && target->width == 960 && target->height == 120);
  assert(!observe(1.5, 0.5, 1)); // no feedback loop
  // A completed resize resets the baseline to new geometry and scale one.
  assert(!policy.observe("scene:1", 960, 120, 1, 1, true, 1));
  assert(!policy.observe("scene:1", 960, 120, 1, 1, true, 1));
  // Continuous drags postpone conversion; a width-only gesture preserves height.
  assert(!observe(1, 1));
  assert(!observe(0.8, 1));
  assert(!observe(0.6, 1));
  assert(!observe(0.5, 1));
  target = observe(0.5, 1, 0.21);
  assert(target && target->width == 320 && target->height == 240);
  assert(!observe(0.5001, 1, 1)); // subpixel noise
  // Unsupported transforms reset pending work rather than replaying it later.
  assert(!observe(0.7, 1));
  assert(!observe(0.7, 1, 1, false));
  assert(!observe(0.7, 1, 1));
  assert(!observe(-1, 1));
  assert(!observe(std::numeric_limits<double>::infinity(), 1));
  assert(!observe(std::numeric_limits<double>::quiet_NaN(), 1));
  assert(!observe(1, 1));
  assert(!observe(100, 0.01));
  target = observe(100, 0.01, 0.21);
  assert(target && target->width == 4096 && target->height == 60);
  // New placement / explicit property changes do not inherit a previous gesture.
  assert(!observe(1.2, 1));
  assert(!policy.observe("other:1", 640, 240, 1.2, 1, true, 1));
  assert(!policy.observe("other:1", 700, 240, 1.2, 1, true, 1));
}
