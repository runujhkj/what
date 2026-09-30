#include "what_overlay/panel/box_logic.h"

#include <cassert>

using what_overlay::panel::SceneItemLabelState;
using what_overlay::panel::box_display_header;
using what_overlay::panel::box_events_url;
using what_overlay::panel::detect_box_kind;
using what_overlay::panel::normalize_label_state_for_enable;

int main() {
  {
    assert(detect_box_kind("http://127.0.0.1:8790/events?box=mic", "") == "mic");
    assert(detect_box_kind("http://127.0.0.1:8790/events?box=desktop", "") == "desktop");
  }
  {
    assert(detect_box_kind("", "What Captions (Mic)") == "mic");
    assert(detect_box_kind("", "what captions (desktop)") == "desktop");
    assert(detect_box_kind("", "Other Source") == "");
  }
  {
    assert(box_events_url("mic") == "http://127.0.0.1:8790/events?box=mic");
    assert(box_events_url("desktop") == "http://127.0.0.1:8790/events?box=desktop");
    assert(box_events_url("other") == "http://127.0.0.1:8790/events?box=other");
    assert(box_events_url("") == "http://127.0.0.1:8790/events");
  }
  {
    assert(box_display_header("mic", true) == "Mic");
    assert(box_display_header("desktop", true) == "Desktop");
    assert(box_display_header("mic", false).empty());
  }
  {
    const SceneItemLabelState in{12, false, -20.0f};
    const SceneItemLabelState out = normalize_label_state_for_enable(in, 4.0f);
    assert(out.crop_top == 0);
    assert(out.bounds_none == true);
    assert(out.pos_y == 4.0f);
  }
  return 0;
}
