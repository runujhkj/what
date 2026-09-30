#include "what_overlay/browser_source.h"
#include "what_overlay/browser/resize_policy.h"
#include <obs-module.h>
#include <graphics/vec2.h>
#include <algorithm>
#include <string>
#include <vector>

namespace what_overlay {
namespace {
struct CaptionBox {
  obs_source_t* source = nullptr;
  obs_source_t* browser = nullptr;
  int width = 640, height = 240;
  bool reflow = true;
  float elapsed = 0;
  browser::ResizePolicy resize;
};

int dimension(obs_data_t* settings, const char* key, int low, int high) {
  return static_cast<int>(std::clamp(obs_data_get_int(settings, key),
                                   static_cast<long long>(low), static_cast<long long>(high)));
}
void defaults(obs_data_t* settings) {
  obs_data_set_default_string(settings, "url", "http://127.0.0.1:8790/caption-box?box=mic&fontSize=32&padding=12");
  obs_data_set_default_int(settings, "width", 640);
  obs_data_set_default_int(settings, "height", 240);
  obs_data_set_default_bool(settings, "drag_reflow", true);
}
obs_data_t* browser_settings(obs_data_t* settings) {
  obs_data_t* child = obs_data_create();
  obs_data_set_string(child, "url", obs_data_get_string(settings, "url"));
  obs_data_set_int(child, "width", dimension(settings, "width", 80, 4096));
  obs_data_set_int(child, "height", dimension(settings, "height", 60, 4096));
  // Width/height-only updates use obs-browser's viewport resize path, not a reload.
  obs_data_set_bool(child, "is_local_file", false);
  obs_data_set_bool(child, "shutdown", false);
  obs_data_set_bool(child, "restart_when_active", false);
  return child;
}
void update(void* data, obs_data_t* settings) {
  auto* box = static_cast<CaptionBox*>(data);
  box->width = dimension(settings, "width", 80, 4096);
  box->height = dimension(settings, "height", 60, 4096);
  box->reflow = obs_data_get_bool(settings, "drag_reflow");
  box->resize.reset();
  if (!box->browser) return;
  auto* child = browser_settings(settings);
  obs_source_update(box->browser, child);
  obs_data_release(child);
}
void* create(obs_data_t* settings, obs_source_t* source) {
  auto* box = new CaptionBox;
  box->source = source;
  auto* child = browser_settings(settings);
  box->browser = obs_source_create_private("browser_source", "What Caption Box Browser", child);
  obs_data_release(child);
  if (!box->browser || !obs_obj_get_data(box->browser)) {
    blog(LOG_ERROR, "[what] What Caption Box requires the OBS Browser Source plugin");
    obs_source_release(box->browser);
    delete box;
    return nullptr;
  }
  obs_source_add_active_child(source, box->browser);
  update(box, settings);
  return box;
}
void destroy(void* data) {
  auto* box = static_cast<CaptionBox*>(data);
  if (box->browser) {
    obs_source_remove_active_child(box->source, box->browser);
    obs_source_release(box->browser);
  }
  delete box;
}
void children(void* data, obs_source_enum_proc_t cb, void* param) {
  auto* box = static_cast<CaptionBox*>(data);
  if (box->browser) cb(box->source, box->browser, param);
}

struct Placement {
  obs_sceneitem_t* item;
  std::string key;
  bool grouped;
};
struct Scan {
  obs_source_t* target;
  std::vector<Placement> places;
  bool grouped = false;
};
bool collect_item(obs_scene_t* scene, obs_sceneitem_t* item, void* data) {
  auto* scan = static_cast<Scan*>(data);
  if (obs_sceneitem_get_source(item) != scan->target) return true;
  obs_sceneitem_addref(item);
  scan->places.push_back({item, std::string(obs_source_get_uuid(obs_scene_get_source(scene))) + ":" +
                                 std::to_string(obs_sceneitem_get_id(item)), scan->grouped});
  return true;
}
bool collect_scene(void* data, obs_source_t* source) {
  if (obs_scene_from_source(source) || obs_group_from_source(source)) {
    auto* sources = static_cast<std::vector<obs_source_t*>*>(data);
    if (auto* ref = obs_source_get_ref(source)) sources->push_back(ref);
  }
  return true;
}
void tick(void* data, float seconds) {
  auto* box = static_cast<CaptionBox*>(data);
  box->elapsed += seconds;
  if (box->elapsed < 0.05f) return;
  const auto elapsed = box->elapsed;
  box->elapsed = 0;
  if (!box->reflow) { box->resize.reset(); return; }

  // Enumerate globally, including secondary canvases. Collect references first so
  // mutations occur outside OBS's source-list and scene enumeration locks.
  std::vector<obs_source_t*> sources;
  obs_enum_all_sources(collect_scene, &sources);
  Scan scan{box->source, {}};
  for (auto* source : sources) {
    auto* scene = obs_scene_from_source(source);
    scan.grouped = !scene;
    if (!scene) scene = obs_group_from_source(source);
    obs_scene_enum_items(scene, collect_item, &scan);
    obs_source_release(source);
  }
  if (scan.places.size() == 1) {
    const auto& placement = scan.places.front();
    auto* item = placement.item;
    vec2 scale;
    obs_sceneitem_get_scale(item, &scale);
    obs_sceneitem_crop crop{};
    obs_sceneitem_get_crop(item, &crop);
    const bool eligible = !placement.grouped && !obs_sceneitem_locked(item) &&
        obs_sceneitem_get_bounds_type(item) == OBS_BOUNDS_NONE &&
        !crop.left && !crop.right && !crop.top && !crop.bottom;
    auto target = box->resize.observe(placement.key, box->width, box->height,
                                      scale.x, scale.y, eligible, elapsed);
    if (target) {
      auto* settings = obs_source_get_settings(box->source);
      obs_data_set_int(settings, "width", target->width);
      obs_data_set_int(settings, "height", target->height);
      update(box, settings);
      obs_source_update(box->source, settings);
      obs_data_release(settings);
      vec2_set(&scale, 1.0f, 1.0f);
      obs_sceneitem_set_scale(item, &scale);
    }
  } else {
    // A source's viewport is shared by all references. Independent layouts need
    // separate sources; changing a shared source here would resize another scene.
    box->resize.reset();
  }
  for (const auto& placement : scan.places) obs_sceneitem_release(placement.item);
}
obs_properties_t* properties(void*) {
  auto* props = obs_properties_create();
  obs_properties_add_text(props, "url", "Caption box URL (copy from what)", OBS_TEXT_DEFAULT);
  obs_properties_add_int(props, "width", "Width", 80, 4096, 1);
  obs_properties_add_int(props, "height", "Height", 60, 4096, 1);
  obs_properties_add_bool(props, "drag_reflow", "Reflow after dragging resize handles");
  obs_properties_add_text(props, "help",
      "Use a /caption-box URL. Drag with Shift to change width and height independently; "
      "after a short pause, text reflows at the URL's fixed font size. "
      "Choose Create new, not Add Existing, for each layout. Add Existing shares the viewport. Automatic reflow skips shared sources, "
      "groups, cropping, flipped sources and bounding-box transforms. "
      "Explicit Width/Height always remain available.", OBS_TEXT_INFO);
  return props;
}
obs_source_info make_info() {
  obs_source_info info{};
  info.id = "what_caption_box";
  info.type = OBS_SOURCE_TYPE_INPUT;
  info.output_flags = OBS_SOURCE_VIDEO | OBS_SOURCE_CUSTOM_DRAW;
  info.get_name = [](void*) { return "What Caption Box"; };
  info.create = create;
  info.destroy = destroy;
  info.update = update;
  info.get_defaults = defaults;
  info.get_properties = properties;
  info.get_width = [](void* data) { return static_cast<uint32_t>(static_cast<CaptionBox*>(data)->width); };
  info.get_height = [](void* data) { return static_cast<uint32_t>(static_cast<CaptionBox*>(data)->height); };
  info.video_render = [](void* data, gs_effect_t*) {
    auto* box = static_cast<CaptionBox*>(data);
    if (box->browser) obs_source_video_render(box->browser);
  };
  info.video_tick = tick;
  info.enum_active_sources = children;
  info.enum_all_sources = children;
  return info;
}
} // namespace
const obs_source_info* get_browser_source_info() {
  static obs_source_info info = make_info();
  return &info;
}
} // namespace what_overlay
