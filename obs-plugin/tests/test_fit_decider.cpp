#include "what_overlay/layout/fit_decider.h"
#include "what_overlay/layout/font_metrics.h"

#include <cassert>
#include <cmath>
#include <iostream>

using what_overlay::layout::FitDecider;
using what_overlay::layout::FitDecisionRequest;
using what_overlay::layout::FontMetrics;
using what_overlay::layout::FontSpec;

static void testNearEdgePhraseStaysOnLine() {
  FontMetrics metrics;
  FitDecider decider(&metrics);
  FontSpec font;
  font.size_px = 32.0;
  const std::string current = "test segment 2 test";
  const std::string token = "segment 4";
  const std::string candidate = current + " " + token;
  const double measured = metrics.measure_text_px(font, candidate);
  const int width = static_cast<int>(std::ceil(measured / 1.20));
  const FitDecisionRequest req{current, token, font, width};
  const auto out = decider.decide(req);
  assert(out.fits);  // Requires width slack in fit_decider.
}

static void testClearlyNarrowWidthStillWraps() {
  FontMetrics metrics;
  FitDecider decider(&metrics);
  FontSpec font;
  font.size_px = 32.0;
  const std::string current = "test segment 2 test";
  const std::string token = "segment 4";
  const std::string candidate = current + " " + token;
  const double measured = metrics.measure_text_px(font, candidate);
  const int width = static_cast<int>(std::floor(measured / 2.0));
  const FitDecisionRequest req{current, token, font, width};
  const auto out = decider.decide(req);
  assert(!out.fits);
}

int main() {
  testNearEdgePhraseStaysOnLine();
  testClearlyNarrowWidthStillWraps();
  std::cout << "test_fit_decider: ok\n";
  return 0;
}
