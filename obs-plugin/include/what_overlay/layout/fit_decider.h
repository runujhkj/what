#pragma once

#include "font_metrics.h"

#include <string>

namespace what_overlay::layout {

struct FitDecisionRequest {
  std::string current_line;
  std::string token;
  FontSpec font;
  int width_px = 640;
};

struct FitDecisionResult {
  bool fits = true;
  std::string candidate_line;
  double measured_px = 0.0;
  double max_px = 0.0;
  std::string reason;
};

class FitDecider {
 public:
  explicit FitDecider(const FontMetrics* font_metrics);

  FitDecisionResult decide(const FitDecisionRequest& request) const;

 private:
  const FontMetrics* font_metrics_;
};

}  // namespace what_overlay::layout
