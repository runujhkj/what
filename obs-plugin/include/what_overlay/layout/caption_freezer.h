#pragma once

#include "fit_decider.h"
#include "font_metrics.h"

#include <string>
#include <vector>

namespace what_overlay::layout {

struct FreezeRequest {
  std::vector<std::string> logical_lines;
  FontSpec font;
  int width_px = 640;
  int max_lines = 3;
  bool no_word_split = true;
  bool preserve_segment_units = false;
  bool collect_trace = false;
};

struct FitTraceEntry {
  std::string logical_line;
  std::string current_line;
  std::string token;
  std::string candidate_line;
  double measured_px = 0.0;
  double max_px = 0.0;
  bool fits = true;
  std::string reason;
};

struct FreezeResult {
  std::vector<std::string> lines;
  bool overflowed = false;
  std::vector<FitTraceEntry> trace;
};

class CaptionFreezer {
 public:
  explicit CaptionFreezer(const FontMetrics* font_metrics);

 FreezeResult freeze(const FreezeRequest& request) const;

 private:
  const FontMetrics* font_metrics_;
  FitDecider fit_decider_;
};

}  // namespace what_overlay::layout
