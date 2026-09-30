#include "what_overlay/layout/caption_freezer.h"
#include "what_overlay/layout/visible_window_policy.h"

#include <algorithm>
#include <cctype>
#include <sstream>

namespace what_overlay::layout {
namespace {

std::vector<std::string> split_words(const std::string& line) {
  std::vector<std::string> out;
  std::stringstream ss(line);
  std::string word;
  while (ss >> word) out.push_back(word);
  return out;
}

bool is_digit_char(char ch) {
  return ch >= '0' && ch <= '9';
}

std::vector<std::string> split_words_or_segment_units(const std::string& line,
                                                      bool preserve_segment_units) {
  if (!preserve_segment_units) return split_words(line);
  std::vector<std::string> out;
  size_t i = 0;
  while (i < line.size()) {
    while (i < line.size() && std::isspace(static_cast<unsigned char>(line[i]))) ++i;
    if (i >= line.size()) break;

    const size_t token_start = i;
    static const std::string kSegmentPrefix = "test segment ";
    const bool looks_like_segment =
        (i + kSegmentPrefix.size() < line.size()) &&
        (line.compare(i, kSegmentPrefix.size(), kSegmentPrefix) == 0);
    if (looks_like_segment) {
      size_t digit_i = i + kSegmentPrefix.size();
      while (digit_i < line.size() && is_digit_char(line[digit_i])) ++digit_i;
      if (digit_i > i + kSegmentPrefix.size()) {
        out.push_back(line.substr(token_start, digit_i - token_start));
        i = digit_i;
        continue;
      }
    }

    while (i < line.size() && !std::isspace(static_cast<unsigned char>(line[i]))) ++i;
    out.push_back(line.substr(token_start, i - token_start));
  }
  return out;
}

std::vector<std::string> wrap_no_split(const FontMetrics* fm, const FontSpec& font,
                                       const FitDecider& fit_decider,
                                       const std::string& line, int width_px,
                                       bool preserve_segment_units,
                                       bool collect_trace,
                                       std::vector<FitTraceEntry>* trace_out) {
  const auto words = split_words_or_segment_units(line, preserve_segment_units);
  if (words.empty()) return {""};
  std::vector<std::string> out;
  std::string cur;
  for (const auto& w : words) {
    if (cur.empty()) {
      if (collect_trace && trace_out) {
        FitDecisionResult first = fit_decider.decide(FitDecisionRequest{"", w, font, width_px});
        trace_out->push_back(FitTraceEntry{
            line, "", w, first.candidate_line, first.measured_px, first.max_px, first.fits, first.reason});
      }
      cur = w;
      continue;
    }
    const FitDecisionResult decision = fit_decider.decide(
        FitDecisionRequest{cur, w, font, width_px});
    if (collect_trace && trace_out) {
      trace_out->push_back(FitTraceEntry{
          line, cur, w, decision.candidate_line, decision.measured_px, decision.max_px, decision.fits, decision.reason});
    }
    if (decision.fits) {
      cur = decision.candidate_line;
      continue;
    }
    out.push_back(cur);
    cur = w;
  }
  if (!cur.empty()) out.push_back(cur);
  return out;
}

std::vector<std::string> wrap_allow_split(const FontMetrics* fm, const FontSpec& font,
                                          const std::string& line, int width_px) {
  const double max_w = static_cast<double>(std::max(24, width_px));
  std::vector<std::string> out;
  std::string cur;
  double cur_w = 0.0;
  for (char ch : line) {
    const std::string s(1, ch);
    const double cw = fm ? fm->measure_text_px(font, s)
                         : (s.size() * std::max(1.0, font.size_px) * 0.49);
    if (!cur.empty() && cur_w + cw > max_w) {
      out.push_back(cur);
      cur.clear();
      cur_w = 0.0;
    }
    cur.push_back(ch);
    cur_w += cw;
  }
  if (!cur.empty()) out.push_back(cur);
  if (out.empty()) out.emplace_back("");
  return out;
}

}  // namespace

CaptionFreezer::CaptionFreezer(const FontMetrics* font_metrics)
    : font_metrics_(font_metrics), fit_decider_(font_metrics) {}

FreezeResult CaptionFreezer::freeze(const FreezeRequest& request) const {
  FreezeResult result;
  const int max_lines = std::max(1, request.max_lines);
  for (const auto& logical : request.logical_lines) {
    std::vector<std::string> wrapped = request.no_word_split
                                           ? wrap_no_split(font_metrics_, request.font, fit_decider_, logical, request.width_px,
                                                           request.preserve_segment_units,
                                                           request.collect_trace, &result.trace)
                                           : wrap_allow_split(font_metrics_, request.font, logical, request.width_px);
    for (auto& l : wrapped) {
      while (!l.empty() && std::isspace(static_cast<unsigned char>(l.back()))) l.pop_back();
      result.lines.push_back(std::move(l));
    }
  }
  const VisibleWindowTrimResult trim =
      trim_oldest_lines(result.lines, max_lines);
  result.overflowed = trim.overflowed;
  return result;
}

}  // namespace what_overlay::layout
