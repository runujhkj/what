#pragma once

// Minimal OBS config for plugin compilation when OBS build config is unavailable.
// These values match a default OBS app install layout and are not used at runtime
// for plugin loading, only for compile-time constants.

#define OBS_DATA_PATH "obs-studio"
#define OBS_PLUGIN_PATH "obs-plugins"
#define OBS_PLUGIN_DESTINATION "obs-plugins"

#define OBS_RELEASE_CANDIDATE 0
#define OBS_BETA 0
