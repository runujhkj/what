#include "what_overlay/overlay_source.h"
#include "what_overlay/browser_source.h"
#if defined(WHAT_OVERLAY_HAS_FRONTEND_PANEL)
#include "what_overlay/overlay_panel.h"
#endif

#include <obs-module.h>

OBS_DECLARE_MODULE()
OBS_MODULE_USE_DEFAULT_LOCALE("what_overlay_plugin", "en-US")

const char* obs_module_description(void) {
  return "What Caption Box browser integration and legacy native captions";
}

bool obs_module_load(void) {
  obs_register_source(what_overlay::get_overlay_source_info());
  obs_register_source(what_overlay::get_browser_source_info());
#if defined(WHAT_OVERLAY_HAS_FRONTEND_PANEL)
  what_overlay::init_overlay_panel();
#endif
  return true;
}

void obs_module_unload(void) {
#if defined(WHAT_OVERLAY_HAS_FRONTEND_PANEL)
  what_overlay::shutdown_overlay_panel();
#endif
}
