#include "what_overlay/layout/caption_freezer.h"
#include "what_overlay/layout/font_metrics.h"

#include <cassert>
#include <iostream>
#include <sstream>
#include <vector>

using what_overlay::layout::CaptionFreezer;
using what_overlay::layout::FontMetrics;
using what_overlay::layout::FreezeRequest;

static void testPreserveSegmentUnits() {
  FontMetrics metrics;
  CaptionFreezer freezer(&metrics);
  FreezeRequest req;
  req.logical_lines = {"test segment 11 test segment 13"};
  req.font.size_px = 32.0;
  req.width_px = 260;
  req.max_lines = 4;
  req.no_word_split = true;
  req.preserve_segment_units = true;
  const auto out = freezer.freeze(req);
  assert(out.lines.size() == 2);
  assert(out.lines[0] == "test segment 11");
  assert(out.lines[1] == "test segment 13");
}

static std::vector<std::string> splitWords(const std::string& text) {
  std::vector<std::string> out;
  std::stringstream ss(text);
  std::string w;
  while (ss >> w) out.push_back(w);
  return out;
}

static void testNoWordSplitPreservesWordTokens() {
  FontMetrics metrics;
  CaptionFreezer freezer(&metrics);
  FreezeRequest req;
  req.logical_lines = {"test segment 3 test segment 5 test segment 7 test segment 9 test segment 11 test segment 13"};
  req.font.size_px = 32.0;
  req.width_px = 260;
  req.max_lines = 8;
  req.no_word_split = true;
  req.preserve_segment_units = false;
  const auto out = freezer.freeze(req);
  std::vector<std::string> observed;
  for (const auto& line : out.lines) {
    const auto tokens = splitWords(line);
    observed.insert(observed.end(), tokens.begin(), tokens.end());
  }
  const auto expected = splitWords(req.logical_lines[0]);
  assert(observed == expected);
}

static void testOverflowDropsOldestWrappedLinesOnly() {
  FontMetrics metrics;
  CaptionFreezer freezer(&metrics);
  FreezeRequest req;
  req.logical_lines = {
      "test segment 1 test segment 3 test segment 5 test segment 7 test segment 9"};
  req.font.size_px = 32.0;
  req.width_px = 260;
  req.max_lines = 99;
  req.no_word_split = true;
  req.preserve_segment_units = false;
  const auto baseline = freezer.freeze(req);
  assert(!baseline.lines.empty());

  req.max_lines = 3;
  const auto out = freezer.freeze(req);
  assert(out.overflowed);
  assert(out.lines.size() == 3);
  assert(baseline.lines.size() > out.lines.size());
  const std::size_t keep = out.lines.size();
  const std::size_t start = baseline.lines.size() - keep;
  for (std::size_t i = 0; i < keep; ++i) {
    assert(out.lines[i] == baseline.lines[start + i]);
  }
}

static void testExactBudgetDoesNotOverflow() {
  FontMetrics metrics;
  CaptionFreezer freezer(&metrics);
  FreezeRequest req;
  req.logical_lines = {"test segment 1 test segment 3"};
  req.font.size_px = 32.0;
  req.width_px = 260;
  req.max_lines = 99;
  req.no_word_split = true;
  req.preserve_segment_units = false;
  const auto baseline = freezer.freeze(req);
  assert(!baseline.overflowed);
  assert(!baseline.lines.empty());

  req.max_lines = static_cast<int>(baseline.lines.size());
  const auto out = freezer.freeze(req);
  assert(!out.overflowed);
  assert(out.lines.size() == baseline.lines.size());
  for (std::size_t i = 0; i < baseline.lines.size(); ++i) {
    assert(out.lines[i] == baseline.lines[i]);
  }
}

int main() {
  testPreserveSegmentUnits();
  testNoWordSplitPreservesWordTokens();
  testOverflowDropsOldestWrappedLinesOnly();
  testExactBudgetDoesNotOverflow();
  std::cout << "test_caption_freezer: ok\n";
  return 0;
}
