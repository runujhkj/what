#pragma once

#include <string>

namespace what_overlay::panel {

std::string detect_box_kind(const std::string& url, const std::string& source_name);
std::string box_events_url(const std::string& box);
std::string box_display_header(const std::string& box, bool with_labels);

struct SceneItemLabelState {
  int crop_top = 0;
  bool bounds_none = true;
  float pos_y = 0.0f;
};

SceneItemLabelState normalize_label_state_for_enable(const SceneItemLabelState& in, float min_y = 4.0f);

}  // namespace what_overlay::panel
