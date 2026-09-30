#include "what_overlay/layout/font_metrics.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>
#include <list>
#include <string>
#include <unordered_map>

namespace what_overlay::layout {
namespace {

double estimate_char_width_px(unsigned char c, double size_px) {
  // Keep estimator aligned with overlay_source wrapping heuristics so measured
  // layout and on-source rendering agree on right-edge fit.
  if (std::isspace(c)) return size_px * 0.30;
  if (std::strchr("ilI|!.,:;'`", static_cast<char>(c))) return size_px * 0.26;
  if (std::strchr("mwMW@#%&", static_cast<char>(c))) return size_px * 0.80;
  if (std::isdigit(c)) return size_px * 0.52;
  if (std::isupper(c)) return size_px * 0.58;
  return size_px * 0.49;
}

std::string make_cache_key(const FontSpec& font, const std::string& text) {
  return font.family + "|" + font.style + "|" + std::to_string(font.flags) + "|" +
         std::to_string(font.size_px) + "|" + text;
}

}  // namespace

struct FontMetrics::Impl {
  std::unordered_map<std::string, std::pair<double, std::list<std::string>::iterator>> cache;
  std::list<std::string> lru;
};

FontMetrics::FontMetrics(std::size_t max_cache_entries)
    : max_cache_entries_(std::max<std::size_t>(64, max_cache_entries)), impl_(new Impl()) {}

FontMetrics::~FontMetrics() {
  delete impl_;
}

double FontMetrics::measure_text_px(const FontSpec& font, const std::string& text) const {
  const std::string key = make_cache_key(font, text);
  auto it = impl_->cache.find(key);
  if (it != impl_->cache.end()) {
    impl_->lru.splice(impl_->lru.begin(), impl_->lru, it->second.second);
    return it->second.first;
  }

  const double size = std::max(1.0, font.size_px);
  double width = 0.0;
  for (unsigned char c : text) width += estimate_char_width_px(c, size);

  impl_->lru.push_front(key);
  impl_->cache[key] = {width, impl_->lru.begin()};
  if (impl_->cache.size() > max_cache_entries_) {
    const std::string& evict = impl_->lru.back();
    impl_->cache.erase(evict);
    impl_->lru.pop_back();
  }
  return width;
}

void FontMetrics::clear_cache() {
  impl_->cache.clear();
  impl_->lru.clear();
}

}  // namespace what_overlay::layout
