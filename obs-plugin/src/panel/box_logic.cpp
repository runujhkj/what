#include "what_overlay/panel/box_logic.h"

#include <algorithm>
#include <cctype>

namespace what_overlay::panel {

std::string detect_box_kind(const std::string& url, const std::string& source_name) {
  // Parse box= query parameter from URL first (authoritative).
  const auto q = url.find('?');
  if (q != std::string::npos) {
    const std::string query = url.substr(q + 1);
    const std::string needle = "box=";
    const auto pos = query.find(needle);
    if (pos != std::string::npos) {
      auto value = query.substr(pos + needle.size());
      const auto amp = value.find('&');
      if (amp != std::string::npos) value = value.substr(0, amp);
      for (auto& ch : value) ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
      if (!value.empty()) return value;
    }
  }
  // Fall back to source-name heuristics for legacy sources without a box= URL parameter.
  std::string name = source_name;
  std::transform(name.begin(), name.end(), name.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (name.find("mic") != std::string::npos) return "mic";
  if (name.find("desktop") != std::string::npos) return "desktop";
  return "";
}

std::string box_events_url(const std::string& box) {
  if (box.empty()) return "http://127.0.0.1:8790/events";
  return "http://127.0.0.1:8790/events?box=" + box;
}

std::string box_display_header(const std::string& box, bool with_labels) {
  if (!with_labels || box.empty()) return "";
  std::string name = box;
  name[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(name[0])));
  return name;
}

SceneItemLabelState normalize_label_state_for_enable(const SceneItemLabelState& in, float min_y) {
  SceneItemLabelState out = in;
  out.crop_top = 0;
  out.bounds_none = true;
  if (out.pos_y < min_y) out.pos_y = min_y;
  return out;
}

}  // namespace what_overlay::panel
