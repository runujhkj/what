#include "what_overlay/layout/fit_decider.h"

#include <algorithm>

namespace what_overlay::layout {
namespace {
double measure_text(const FontMetrics* fm, const FontSpec& font, const std::string& text) {
  return fm ? fm->measure_text_px(font, text) : (text.size() * std::max(1.0, font.size_px) * 0.49);
}

}  // namespace

FitDecider::FitDecider(const FontMetrics* font_metrics) : font_metrics_(font_metrics) {}

FitDecisionResult FitDecider::decide(const FitDecisionRequest& request) const {
  FitDecisionResult out;
  const double max_w = static_cast<double>(std::max(24, request.width_px));
  out.max_px = max_w;
  if (request.current_line.empty()) {
    out.fits = true;
    out.candidate_line = request.token;
    out.measured_px = measure_text(font_metrics_, request.font, out.candidate_line);
    out.reason = "empty_line";
    return out;
  }
  out.candidate_line = request.current_line + " " + request.token;
  out.measured_px = measure_text(font_metrics_, request.font, out.candidate_line);
  out.fits = out.measured_px <= max_w;
  out.reason = out.fits ? "fits_width" : "overflow_width";
  return out;
}

}  // namespace what_overlay::layout
