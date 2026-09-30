// Exercise the real libobs scene/settings adapter with a lightweight browser stand-in.
// CEF drawing and mouse gestures still require the live OBS acceptance check.
#include "what_overlay/browser_source.h"
#include <obs.h>
#include <graphics/vec2.h>
#include <cassert>
#include <cstring>

static obs_source_t* child = nullptr;
static int destroyed = 0;
int main() {
  assert(obs_startup("en-US", nullptr, nullptr));
  // No GPU/video output in this adapter test; avoid relative coordinates on a zero-size canvas.
  auto* config = obs_data_create();
  obs_data_set_bool(config, "AbsoluteCoordinates", true);
  obs_apply_private_data(config);
  obs_data_release(config);
  obs_source_info fake{};
  fake.id = "browser_source";
  fake.type = OBS_SOURCE_TYPE_INPUT;
  fake.output_flags = OBS_SOURCE_VIDEO;
  fake.get_name = [](void*) { return "Test browser"; };
  fake.create = [](obs_data_t*, obs_source_t* source) -> void* { child = source; return source; };
  fake.destroy = [](void*) { ++destroyed; };
  fake.get_width = [](void*) -> uint32_t { return 640; };
  fake.get_height = [](void*) -> uint32_t { return 240; };
  obs_register_source(&fake);
  const auto* info = what_overlay::get_browser_source_info();
  obs_register_source(info);
  auto* source = obs_source_create("what_caption_box", "Caption test", nullptr, nullptr);
  assert(source && child);
  auto* data = obs_obj_get_data(source);
  auto* scene = obs_scene_create("Test scene");
  auto* item = obs_scene_add(scene, source);
  vec2 position; vec2_set(&position, 100, 200);
  obs_sceneitem_set_pos(item, &position);
  obs_sceneitem_set_rot(item, 15);
  auto tick = [&] { info->video_tick(data, 0.11f); };
  auto scale = [&](float x, float y) { vec2 value; vec2_set(&value, x, y); obs_sceneitem_set_scale(item, &value); };
  auto size = [&] (int w, int h) {
    assert(obs_source_get_width(source) == static_cast<uint32_t>(w));
    assert(obs_source_get_height(source) == static_cast<uint32_t>(h));
    auto* settings = obs_source_get_settings(child);
    assert(obs_data_get_int(settings, "width") == w);
    assert(obs_data_get_int(settings, "height") == h);
    assert(std::strstr(obs_data_get_string(settings, "url"), "fontSize=32"));
    obs_data_release(settings);
  };
  tick(); scale(0.5f, 1); tick(); tick(); tick();
  size(320, 240);
  vec2 current; obs_sceneitem_get_scale(item, &current);
  assert(current.x == 1 && current.y == 1);
  obs_sceneitem_get_pos(item, &position);
  assert(position.x == 100 && position.y == 200 && obs_sceneitem_get_rot(item) == 15);
  auto* saved = obs_source_get_settings(source);
  assert(obs_data_get_int(saved, "width") == 320);
  obs_data_release(saved);
  tick(); tick(); size(320, 240); // normalized transform does not bounce back

  obs_sceneitem_set_locked(item, true);
  scale(1.5f, 1); tick(); tick(); tick(); size(320, 240);
  obs_sceneitem_set_locked(item, false);
  tick();
  obs_sceneitem_set_bounds_type(item, OBS_BOUNDS_STRETCH);
  scale(2, 1); tick(); tick(); tick(); size(320, 240);
  obs_sceneitem_set_bounds_type(item, OBS_BOUNDS_NONE);
  tick();

  // References in any scene block mutation of the shared viewport.
  auto* second = obs_scene_create("Other layout");
  auto* reference = obs_scene_add(second, source);
  tick(); scale(2, 2); tick(); tick(); tick(); size(320, 240);
  obs_sceneitem_remove(reference); obs_scene_release(second);
  obs_wait_for_destroy_queue();
  tick(); tick(); size(320, 240); // removing the reference isn't a new drag

  // Crop gestures are left intact.
  obs_sceneitem_crop crop{10, 0, 0, 0};
  obs_sceneitem_set_crop(item, &crop);
  scale(1.5f, 1); tick(); tick(); tick(); size(320, 240);
  crop = {}; obs_sceneitem_set_crop(item, &crop);
  tick(); scale(1, 0.5f); tick(); tick(); tick(); size(320, 120);

  auto* options = obs_source_get_settings(source);
  obs_data_set_bool(options, "drag_reflow", false);
  info->update(data, options);
  scale(2, 2); tick(); tick(); tick(); size(320, 120);
  obs_data_set_int(options, "width", 800);
  info->update(data, options);
  size(800, 120); // explicit dimensions still work with drag conversion disabled
  obs_data_release(options);

  obs_sceneitem_remove(item);
  obs_scene_release(scene);
  obs_wait_for_destroy_queue();

  // A separate canvas must be discovered without frontend/main-scene enumeration.
  auto* canvas = obs_canvas_create("Vertical test", nullptr, 0);
  assert(canvas);
  auto* vertical_scene = obs_canvas_scene_create(canvas, "Vertical scene");
  assert(vertical_scene);
  item = obs_scene_add(vertical_scene, source);
  options = obs_source_get_settings(source);
  obs_data_set_bool(options, "drag_reflow", true);
  info->update(data, options);
  obs_data_release(options);
  tick(); scale(0.5f, 3); tick(); tick(); tick();
  size(400, 360);
  obs_sceneitem_get_scale(item, &current);
  assert(current.x == 1 && current.y == 1);
  tick(); scale(1.5f, 0.5f); tick(); tick(); tick();
  size(600, 180);
  obs_sceneitem_get_scale(item, &current);
  assert(current.x == 1 && current.y == 1);
  obs_sceneitem_remove(item);
  obs_scene_release(vertical_scene);
  obs_wait_for_destroy_queue();
  obs_canvas_remove(canvas);
  obs_canvas_release(canvas);
  obs_source_release(source);
  obs_wait_for_destroy_queue();
  obs_shutdown();
  assert(destroyed == 1);
}
