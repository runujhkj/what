#pragma once

#include <cstddef>
#include <string>

namespace what_overlay::layout {

struct FontSpec {
  std::string family = "Helvetica";
  std::string style;
  double size_px = 32.0;
  int flags = 0;
};

class FontMetrics {
 public:
  explicit FontMetrics(std::size_t max_cache_entries = 4096);
  ~FontMetrics();

  FontMetrics(const FontMetrics&) = delete;
  FontMetrics& operator=(const FontMetrics&) = delete;

  double measure_text_px(const FontSpec& font, const std::string& text) const;
  void clear_cache();

 private:
  struct Impl;
  std::size_t max_cache_entries_;
  mutable Impl* impl_;
};

}  // namespace what_overlay::layout
