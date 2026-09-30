#include "what_overlay/overlay_source.h"
#include "what_overlay/overlay_state.h"
#include "what_overlay/layout/font_metrics.h"
#include "what_overlay/layout/caption_freezer.h"
#include "what_overlay/layout/line_layout.h"
#include "what_overlay/layout/overlay_label_policy.h"
#include "what_overlay/layout/header_render_policy.h"
#include "what_overlay/layout/body_render_pipeline.h"
#include "what_overlay/layout/source_render_policy.h"
#include "what_overlay/layout/text_wrap_utils.h"
#include "what_overlay/pipeline/payload_ingest_policy.h"
#include "what_overlay/pipeline/control_http_client.h"
#include "what_overlay/pipeline/header_activation_policy.h"
#include "what_overlay/pipeline/header_source_sync_policy.h"
#include "what_overlay/pipeline/transition_policy.h"
#include "what_overlay/pipeline/render_geometry_policy.h"
#include "what_overlay/pipeline/body_source_update_policy.h"
#include "what_overlay/pipeline/body_fit_policy.h"
#include "what_overlay/pipeline/body_text_fit_inputs.h"
#include "what_overlay/pipeline/legacy_wrap_policy.h"
#include "what_overlay/pipeline/payload_json_parser.h"
#include "what_overlay/pipeline/runtime_adapter.h"

#include <obs-module.h>
#include <obs.h>
#include <util/platform.h>

#include <cctype>
#include <cmath>
#include <algorithm>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace what_overlay {

static void overlay_update(void* data, obs_data_t* settings);
static void overlay_apply_pending(void* param);
static void overlay_sync_from_shared_state(OverlaySource* ctx);

namespace {
constexpr double kCharWidthEstimate = 0.49;
constexpr double kWrapSlack = 2.10;
constexpr double kObsFontScale = 6.0;
constexpr const char* kOverlayBuildStamp = "label-debug-2026-03-04-b";

static int content_width_px(const OverlaySource* ctx) {
  if (!ctx) return 24;
  return std::max(24, ctx->config.width_px - (ctx->config.padding_x_px * 2));
}

static int content_height_px(const OverlaySource* ctx) {
  if (!ctx) return 24;
  return std::max(24, ctx->config.height_px - (ctx->config.padding_y_px * 2));
}

static int outline_thickness_px(const OverlaySource* ctx) {
  if (!ctx || !ctx->config.outline_enabled) return 0;
  return std::max(1, std::min(24, ctx->config.outline_thickness_px));
}

static std::string active_header_text(const OverlaySource* ctx) {
  if (!ctx) return "";
  const auto activation = pipeline::adapt_header_activation(
      ctx->config,
      ctx->current_header,
      layout::HeaderSourceAvailability{
          ctx->overflow_source != nullptr,
          ctx->text_enter != nullptr,
          ctx->header_source != nullptr,
          ctx->text_prev != nullptr,
      },
      layout::HeaderSourceMode::kStrictHeaderOnly);
  return activation.active_header;
}

static int label_font_units(const OverlaySource* ctx) {
  if (!ctx) return 0;
  return layout::compute_label_font_units(ctx->config.font_size_px, active_header_text(ctx));
}

static int label_font_units_for_header(const OverlaySource* ctx, const std::string& header) {
  if (!ctx) return 0;
  return layout::compute_label_font_units(ctx->config.font_size_px, header);
}

static int label_height_px(const OverlaySource* ctx) {
  if (!ctx) return 0;
  return layout::compute_label_height_px(ctx->config.font_size_px, active_header_text(ctx));
}

static int top_extra_px(const OverlaySource* ctx) {
  if (!ctx) return 0;
  return pipeline::adapt_render_geometry(ctx->config, active_header_text(ctx)).top_extra_px;
}

// Per-render diagnostics are off unless asked for. The block they guard is not just
// blog() calls: it makes eight obs_source_get_width/height calls, builds two text
// previews and formats two ~320-byte lines EVERY render, on the graphics thread. On a
// 1080p60 scene with several of these sources that is pure overhead, and OBS logging is
// synchronous disk I/O on top. Compile with -DWHAT_OVERLAY_DEBUG for always-on, or set
// WHAT_OVERLAY_DEBUG_LOG=1 to turn it on in the field without a rebuild.
static bool debug_logging_enabled() {
  static const bool enabled = [] {
#if defined(WHAT_OVERLAY_DEBUG)
    return true;
#else
    const char* v = std::getenv("WHAT_OVERLAY_DEBUG_LOG");
    return v && *v && std::strcmp(v, "0") != 0;
#endif
  }();
  return enabled;
}


static const char* source_label(const OverlaySource* ctx) {
  if (!ctx || ctx->source_name.empty()) return "(unknown)";
  return ctx->source_name.c_str();
}

static const char* obs_source_name_or_unknown(obs_source_t* source) {
  if (!source) return "(null)";
  const char* name = obs_source_get_name(source);
  return (name && *name) ? name : "(unnamed)";
}

static const char* obs_source_id_or_unknown(obs_source_t* source) {
  if (!source) return "(null)";
  const char* id = obs_source_get_id(source);
  return (id && *id) ? id : "(unknown)";
}

static void update_header_source(OverlaySource* ctx, const std::string& header);

static obs_source_t* source_from_role(OverlaySource* ctx, layout::HeaderSourceRole role) {
  if (!ctx) return nullptr;
  switch (role) {
    case layout::HeaderSourceRole::kHeader:
      return ctx->header_source;
    case layout::HeaderSourceRole::kEnter:
      return ctx->text_enter;
    case layout::HeaderSourceRole::kPrev:
      return ctx->text_prev;
    case layout::HeaderSourceRole::kOverflow:
      return ctx->overflow_source;
    case layout::HeaderSourceRole::kNone:
    default:
      return nullptr;
  }
}

static obs_source_t* header_render_source(OverlaySource* ctx) {
  if (!ctx) return nullptr;
  const auto activation = pipeline::adapt_header_activation(
      ctx->config,
      ctx->current_header,
      layout::HeaderSourceAvailability{
          ctx->overflow_source != nullptr,
          ctx->text_enter != nullptr,
          ctx->header_source != nullptr,
          ctx->text_prev != nullptr,
      },
      layout::HeaderSourceMode::kStrictHeaderOnly);
  return source_from_role(ctx, activation.source_role);
}

static obs_source_t* header_update_source(OverlaySource* ctx) {
  if (!ctx) return nullptr;
  // Header text mutations must only target the dedicated header source.
  // Rendering may choose a fallback source in compat paths, but update/repair
  // should never rewrite body/transition text sources.
  return ctx->header_source;
}

static std::string first_line_preview(const std::string& text) {
  if (text.empty()) return "";
  const std::size_t nl = text.find('\n');
  std::string out = (nl == std::string::npos) ? text : text.substr(0, nl);
  if (out.size() > 80) out = out.substr(0, 80);
  return out;
}

static std::string join_lines_with_delim(const std::vector<std::string>& lines,
                                         const char* delim) {
  if (lines.empty()) return "";
  std::string out;
  for (size_t i = 0; i < lines.size(); ++i) {
    if (i != 0 && delim) out += delim;
    out += lines[i];
  }
  return out;
}

static std::string source_text_preview(obs_source_t* source) {
  if (!source) return "";
  obs_data_t* settings = obs_source_get_settings(source);
  if (!settings) return "";
  const char* text = obs_data_get_string(settings, "text");
  const std::string preview = first_line_preview(text ? text : "");
  obs_data_release(settings);
  return preview;
}

static void ensure_header_source_label(OverlaySource* ctx,
                                       const std::string& active_header) {
  if (!ctx) return;
  obs_source_t* source = header_update_source(ctx);
  if (!source) return;
  const std::string preview = source_text_preview(source);
  const auto decision = pipeline::compute_header_source_sync_decision(
      pipeline::HeaderSourceSyncInput{active_header, preview});
  if (!decision.should_repair) return;
  blog(LOG_INFO,
       "what_overlay: header_source_repair src='%s' seq=%d trace='%s' active='%s' preview='%s'",
       source_label(ctx),
       ctx->current_seq,
       ctx->current_trace_id.c_str(),
       active_header.c_str(),
       preview.c_str());
  update_header_source(ctx, active_header);
}

static double ui_font_to_px(double ui_size) {
  // Keep layout math aligned with rendered glyph scale in OBS text source.
  return std::max(1.0, ui_size * kObsFontScale);
}

static double estimate_char_width_px(char c, double font_size_px) {
  const unsigned char uc = static_cast<unsigned char>(c);
  if (std::isspace(uc)) return font_size_px * 0.30;
  if (std::strchr("ilI|!.,:;'`", c)) return font_size_px * 0.26;
  if (std::strchr("mwMW@#%&", c)) return font_size_px * 0.80;
  if (std::isdigit(uc)) return font_size_px * 0.52;
  if (std::isupper(uc)) return font_size_px * 0.58;
  return font_size_px * kCharWidthEstimate;
}

static double estimate_text_width_px(const std::string& text, double font_size_px) {
  double width = 0.0;
  for (char c : text) width += estimate_char_width_px(c, font_size_px);
  return width;
}

// JSON payload parsing and control HTTP helpers were extracted to pipeline modules.

static std::string align_wrapped_lines(const std::string& input, int width_px,
                                       double font_size_px, const std::string& align_mode) {
  if (input.empty() || align_mode == "left") return input;
  const double font_px = ui_font_to_px(font_size_px > 0.0 ? font_size_px : 2.0);
  const double width_limit = std::max(24.0, static_cast<double>(width_px)) * kWrapSlack;
  const double space_w = std::max(1.0, estimate_char_width_px(' ', font_px));
  auto lines = layout::split_lines(input);
  for (size_t i = 0; i < lines.size(); ++i) {
    std::string& line = lines[i];
    if (line.empty()) continue;
    while (!line.empty() && std::isspace(static_cast<unsigned char>(line.back()))) {
      line.pop_back();
    }
    const double line_w = estimate_text_width_px(line, font_px);
    if (align_mode == "center" || align_mode == "right") {
      const double slack = std::max(0.0, width_limit - line_w);
      int pad_spaces = static_cast<int>(std::floor(slack / space_w));
      if (align_mode == "center") pad_spaces /= 2;
      pad_spaces = std::max(0, std::min(120, pad_spaces));
      if (pad_spaces > 0) line.insert(0, static_cast<size_t>(pad_spaces), ' ');
      continue;
    }
    if (align_mode == "justify") {
      if (i + 1 == lines.size()) continue;  // keep final line ragged-right
      std::vector<std::string> words;
      std::string word;
      for (char c : line) {
        if (std::isspace(static_cast<unsigned char>(c))) {
          if (!word.empty()) {
            words.push_back(word);
            word.clear();
          }
        } else {
          word.push_back(c);
        }
      }
      if (!word.empty()) words.push_back(word);
      if (words.size() < 2) continue;
      double words_w = 0.0;
      for (const auto& w : words) words_w += estimate_text_width_px(w, font_px);
      const int gaps = static_cast<int>(words.size()) - 1;
      int total_spaces = static_cast<int>(std::floor(std::max(0.0, width_limit - words_w) / space_w));
      // Cap expansion so justification does not push beyond visual bounds
      // when estimator drift appears on some typefaces.
      total_spaces = std::max(gaps, std::min(120, total_spaces));
      const int base = total_spaces / gaps;
      int extra = total_spaces % gaps;
      std::string rebuilt;
      for (int gi = 0; gi < gaps; ++gi) {
        rebuilt += words[static_cast<size_t>(gi)];
        int gap_count = base + (extra > 0 ? 1 : 0);
        if (extra > 0) extra--;
        rebuilt.append(static_cast<size_t>(gap_count), ' ');
      }
      rebuilt += words.back();
      line = std::move(rebuilt);
    }
  }
  std::string out;
  for (size_t i = 0; i < lines.size(); ++i) {
    if (i != 0) out.push_back('\n');
    out += lines[i];
  }
  return out;
}

struct BoxTextResult {
  std::string visible;
  std::string full_wrapped;
  bool overflowed = false;
  double render_font_size = 32.0;
};

static BoxTextResult fit_text_to_box(const std::string& input, int width_px, int height_px, double font_size_px,
                                     int max_visible_lines, bool auto_shrink_to_fit, bool no_word_split) {
  BoxTextResult result;
  const double min_font = 0.5;
  double font = font_size_px > 0.0 ? font_size_px : 2.0;

  const std::string semantic = pipeline::limit_tail_lines_for_fit(input, std::max(1, max_visible_lines));
  const std::string wrap_input = pipeline::normalize_soft_breaks_for_fit(semantic);
  std::string rendered = no_word_split
                             ? pipeline::wrap_text_legacy_word_boundary(
                                   wrap_input, width_px, font, kWrapSlack, kObsFontScale)
                             : pipeline::wrap_text_legacy_allow_split(
                                   wrap_input, width_px, font, kWrapSlack, kObsFontScale);
  auto lines = layout::split_lines(rendered);
  int max_lines = std::max(1, std::min(std::max(1, max_visible_lines),
                                       pipeline::calc_max_lines_for_height(height_px, font, kObsFontScale)));

  if (auto_shrink_to_fit) {
    while (static_cast<int>(lines.size()) > max_lines && font > min_font) {
      font = std::max(min_font, font - 0.5);
      rendered = no_word_split
                     ? pipeline::wrap_text_legacy_word_boundary(
                           wrap_input, width_px, font, kWrapSlack, kObsFontScale)
                     : pipeline::wrap_text_legacy_allow_split(
                           wrap_input, width_px, font, kWrapSlack, kObsFontScale);
      lines = layout::split_lines(rendered);
      max_lines = std::max(
          1, std::min(std::max(1, max_visible_lines),
                      pipeline::calc_max_lines_for_height(height_px, font, kObsFontScale)));
    }
  }

  result.full_wrapped = rendered;
  result.render_font_size = font;
  if (static_cast<int>(lines.size()) > max_lines) {
    result.overflowed = true;
    result.visible = layout::join_lines_from(lines, lines.size() - static_cast<size_t>(max_lines));
  } else {
    result.visible = rendered;
  }
  return result;
}

static uint32_t parse_color_rgba(const std::string& hex) {
  if (hex.empty()) return 0xFFFFFFFF;
  std::string value = hex;
  if (value[0] == '#') value.erase(0, 1);
  if (value.size() != 6 && value.size() != 8) return 0xFFFFFFFF;
  uint32_t raw = 0;
  try {
    raw = static_cast<uint32_t>(std::stoul(value, nullptr, 16));
  } catch (...) {
    return 0xFFFFFFFF;
  }
  uint8_t a = 0xFF;
  uint8_t r = 0;
  uint8_t g = 0;
  uint8_t b = 0;
  if (value.size() == 6) {
    r = static_cast<uint8_t>((raw >> 16) & 0xFF);
    g = static_cast<uint8_t>((raw >> 8) & 0xFF);
    b = static_cast<uint8_t>(raw & 0xFF);
  } else {
    a = static_cast<uint8_t>((raw >> 24) & 0xFF);
    r = static_cast<uint8_t>((raw >> 16) & 0xFF);
    g = static_cast<uint8_t>((raw >> 8) & 0xFF);
    b = static_cast<uint8_t>(raw & 0xFF);
  }
  // Parsed form is AARRGGBB (ARGB).
  return (static_cast<uint32_t>(a) << 24) |
         (static_cast<uint32_t>(r) << 16) |
         (static_cast<uint32_t>(g) << 8) |
         static_cast<uint32_t>(b);
}

static uint32_t argb_to_abgr(uint32_t argb) {
  const uint8_t a = static_cast<uint8_t>((argb >> 24) & 0xFF);
  const uint8_t r = static_cast<uint8_t>((argb >> 16) & 0xFF);
  const uint8_t g = static_cast<uint8_t>((argb >> 8) & 0xFF);
  const uint8_t b = static_cast<uint8_t>(argb & 0xFF);
  return (static_cast<uint32_t>(a) << 24) |
         (static_cast<uint32_t>(b) << 16) |
         (static_cast<uint32_t>(g) << 8) |
         static_cast<uint32_t>(r);
}

static uint32_t parse_text_color_for_obs(const std::string& hex) {
  return argb_to_abgr(parse_color_rgba(hex));
}

static uint32_t parse_bg_color_for_render(const std::string& hex) {
  return argb_to_abgr(parse_color_rgba(hex));
}

static BoxTextResult fit_text_to_box_dispatch(
    OverlaySource* ctx, const std::string& input, int width_px, int height_px,
    double font_size_px, int max_visible_lines, bool auto_shrink_to_fit, bool no_word_split) {
  BoxTextResult result;
  const double effective_font_ui = pipeline::resolve_effective_font_ui(font_size_px, auto_shrink_to_fit);
  const std::string align_mode = ctx ? ctx->config.align : "left";
  if (!ctx || !pipeline::should_use_measured_layout(ctx->config)) {
    const BoxTextResult legacy =
        fit_text_to_box(input, width_px, height_px, effective_font_ui, max_visible_lines, false,
                        no_word_split);
    result = legacy;
    // For left/center/right, let OBS text source perform alignment inside the
    // configured extents. Keep manual spacing only for justify.
    if (align_mode == "justify") {
      result.visible = align_wrapped_lines(result.visible, width_px, result.render_font_size, "justify");
      result.full_wrapped = align_wrapped_lines(result.full_wrapped, width_px, result.render_font_size, "justify");
    }
    return result;
  }

  static layout::FontMetrics metrics(4096);
  static layout::CaptionFreezer freezer(&metrics);
  double measured_font_ui = effective_font_ui;
  layout::FreezeRequest req = pipeline::build_measured_freeze_request(
      ctx->config,
      layout::split_lines(pipeline::normalize_soft_breaks_for_fit(input)),
      width_px,
      height_px,
      measured_font_ui > 0.0 ? measured_font_ui : 2.0,
      max_visible_lines,
      no_word_split,
      kObsFontScale);
#ifdef what_overlay_debug
  req.collect_trace = true;
#endif

  const layout::FreezeResult frozen = freezer.freeze(req);
#ifdef what_overlay_debug
  for (const auto& entry : frozen.trace) {
    blog(LOG_INFO,
         "what_overlay: fit_decider line='%s' current='%s' token='%s' candidate='%s' measured=%.2f max=%.2f fits=%s reason=%s",
         entry.logical_line.c_str(), entry.current_line.c_str(), entry.token.c_str(),
         entry.candidate_line.c_str(), entry.measured_px, entry.max_px,
         entry.fits ? "yes" : "no", entry.reason.c_str());
  }
#endif
  result.overflowed = frozen.overflowed;
  result.render_font_size = measured_font_ui > 0.0 ? measured_font_ui : 2.0;

  std::vector<std::string> output_lines;
  output_lines.reserve(frozen.lines.size());
  for (const auto& line : frozen.lines) {
    std::string out = line;
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.back()))) out.pop_back();
    output_lines.push_back(std::move(out));
  }
  const std::string joined = layout::join_lines_all(output_lines);
  result.visible = (align_mode == "justify")
                       ? align_wrapped_lines(joined, width_px, result.render_font_size, "justify")
                       : joined;
  result.full_wrapped = result.visible;
  return result;
}

static void update_text_source(OverlaySource* ctx, obs_source_t* target, const std::string& text,
                               const std::string& header) {
  if (!ctx || !target) return;
  obs_data_t* settings = obs_source_get_settings(target);
  std::string body = layout::prepare_body_text_input(
      text, header, ctx->config.header, ctx->config.uppercase);
  const int content_w = content_width_px(ctx);
  const int content_h = content_height_px(ctx);
  const int max_visible_lines = std::max(1, ctx->config.max_segments);
  const bool effective_no_word_split = ctx->config.no_word_split;
  const BoxTextResult fitted = fit_text_to_box_dispatch(
      ctx, body, content_w, content_h, ctx->config.font_size_px, max_visible_lines,
      ctx->config.auto_shrink_to_fit, effective_no_word_split);
  const auto post = layout::finalize_body_visible_text(fitted.visible, header, ctx->config.header);
  std::string final_visible = post.text;
  if (post.contains_label_token) {
    blog(LOG_INFO,
         "what_overlay: body_contains_label_token path=text visible='%s' header='%s' cfg_header='%s'",
         final_visible.c_str(), header.c_str(), ctx->config.header.c_str());
  }
  blog(LOG_INFO, "what_overlay: final_body src='%s' seq=%d trace='%s' path=text len=%zu first='%s' header='%s' cfg_header='%s'",
       source_label(ctx), ctx->current_seq, ctx->current_trace_id.c_str(),
       final_visible.size(), first_line_preview(final_visible).c_str(), header.c_str(), ctx->config.header.c_str());
  ctx->overflowed = fitted.overflowed;
#ifdef what_overlay_debug
  blog(LOG_INFO, "what_overlay: update_text_source len=%zu header_len=%zu",
       fitted.visible.size(), ctx->config.header.size());
#endif
  const auto update_spec = pipeline::build_body_source_update_spec(
      ctx->config,
      content_w,
      content_h,
      fitted.render_font_size > 0.0 ? fitted.render_font_size : 32.0,
      ctx->text_color,
      kObsFontScale);
  obs_data_set_bool(settings, "from_file", update_spec.from_file);
  obs_data_set_bool(settings, "word_wrap", update_spec.word_wrap);
  obs_data_set_bool(settings, "no_word_split", update_spec.no_word_split);
  obs_data_set_int(settings, "custom_width", update_spec.custom_width);
  obs_data_set_bool(settings, "extents", update_spec.extents);
  obs_data_set_int(settings, "extents_cx", update_spec.extents_cx);
  obs_data_set_int(settings, "extents_cy", update_spec.extents_cy);
  obs_data_set_string(settings, "text", final_visible.c_str());
  obs_data_set_string(settings, "align", update_spec.align.c_str());
  obs_data_set_int(settings, "color1", update_spec.color1);
  obs_data_set_int(settings, "color2", update_spec.color2);

  obs_data_t* font = obs_data_create();
  obs_data_set_string(font, "face", update_spec.font_face.c_str());
  obs_data_set_int(font, "size", update_spec.font_units);
  obs_data_set_int(font, "flags", update_spec.font_flags);
  obs_data_set_string(font, "style", update_spec.font_style.c_str());
  obs_data_set_obj(settings, "font", font);
  obs_data_release(font);

  obs_source_update(target, settings);
  obs_data_release(settings);
  ctx->shared_state_version = overlay_state_set_effective_font_size(fitted.render_font_size);
  std::vector<std::string> seg_ids = ctx ? ctx->current_segment_ids : std::vector<std::string>{};
  std::vector<std::string> seg_texts = ctx ? ctx->current_segments : std::vector<std::string>{};
  if (seg_ids.size() != seg_texts.size()) {
    seg_ids.clear();
    seg_texts.clear();
  }
  if (seg_ids.empty()) {
    seg_texts = layout::split_lines(final_visible);
    seg_ids.resize(seg_texts.size());
    for (size_t i = 0; i < seg_ids.size(); ++i) seg_ids[i] = "line-" + std::to_string(i);
  }
  auto spans = ctx ? ctx->current_spans : std::vector<OverlayRenderedSpan>{};
  if (spans.empty()) {
    spans = pipeline::compute_rendered_spans(final_visible, seg_ids, seg_texts);
  }
  overlay_state_set_rendered_output(final_visible, seg_ids, seg_texts, spans);
}

static void update_text_source_lines(
    OverlaySource* ctx, obs_source_t* target, const std::vector<std::string>& lines, const std::string& header) {
  if (!ctx || !target) return;
  obs_data_t* settings = obs_source_get_settings(target);
  const layout::LineBreakPolicy effective_break_policy = layout::LineBreakPolicy::kPreserveInput;
  // Preserve upstream line-freeze composition for lines-mode updates so
  // sealed-line rollover remains stable and does not reflow prior content.
  const std::string body = layout::prepare_body_lines_input(
      lines, header, ctx->config.header, ctx->config.uppercase, effective_break_policy);
  const int content_w = content_width_px(ctx);
  const int content_h = content_height_px(ctx);
  // Lines-mode payloads are already lane-composed by upstream policy. Do not
  // run a second wrapping/freeze pass here or words can reshuffle/split again.
  std::string visible_text = body;
  if (ctx->config.align == "justify") {
    visible_text = align_wrapped_lines(visible_text, content_w, ctx->config.font_size_px, "justify");
  }
  const auto post = layout::finalize_body_visible_text(visible_text, header, ctx->config.header);
  visible_text = post.text;
  {
    if (post.contains_label_token) {
      blog(LOG_INFO,
           "what_overlay: body_contains_label_token path=lines visible='%s' header='%s' cfg_header='%s'",
           visible_text.c_str(), header.c_str(), ctx->config.header.c_str());
    }
  }
  blog(LOG_INFO, "what_overlay: final_body src='%s' seq=%d trace='%s' path=lines len=%zu first='%s' header='%s' cfg_header='%s'",
       source_label(ctx), ctx->current_seq, ctx->current_trace_id.c_str(),
       visible_text.size(), first_line_preview(visible_text).c_str(), header.c_str(), ctx->config.header.c_str());
  blog(LOG_INFO,
       "what_overlay: final_body_lines src='%s' seq=%d trace='%s' lines='%s'",
       source_label(ctx),
       ctx->current_seq,
       ctx->current_trace_id.c_str(),
       join_lines_with_delim(post.lines, " || ").c_str());
  ctx->overflowed = false;
  const double render_font_size = ctx->config.font_size_px;
  const auto update_spec = pipeline::build_body_source_update_spec(
      ctx->config,
      content_w,
      content_h,
      render_font_size,
      ctx->text_color,
      kObsFontScale);
  obs_data_set_bool(settings, "from_file", update_spec.from_file);
  // Lines-mode text is already lane-composed upstream. Keep OBS from
  // re-wrapping and reshuffling frozen lines.
  obs_data_set_bool(settings, "word_wrap", false);
  obs_data_set_bool(settings, "no_word_split", update_spec.no_word_split);
  obs_data_set_int(settings, "custom_width", update_spec.custom_width);
  obs_data_set_bool(settings, "extents", update_spec.extents);
  obs_data_set_int(settings, "extents_cx", update_spec.extents_cx);
  obs_data_set_int(settings, "extents_cy", update_spec.extents_cy);
  obs_data_set_string(settings, "text", visible_text.c_str());
  obs_data_set_string(settings, "align", update_spec.align.c_str());
  obs_data_set_int(settings, "color1", update_spec.color1);
  obs_data_set_int(settings, "color2", update_spec.color2);

  obs_data_t* font = obs_data_create();
  obs_data_set_string(font, "face", update_spec.font_face.c_str());
  obs_data_set_int(font, "size", update_spec.font_units);
  obs_data_set_int(font, "flags", update_spec.font_flags);
  obs_data_set_string(font, "style", update_spec.font_style.c_str());
  obs_data_set_obj(settings, "font", font);
  obs_data_release(font);
  obs_source_update(target, settings);
  obs_data_release(settings);
  blog(LOG_INFO,
       "what_overlay: body_source_updated src='%s' seq=%d trace='%s' target=%p target_name='%s' target_id='%s' lines_n=%zu first='%s' dims=%ux%u",
       source_label(ctx),
       ctx->current_seq,
       ctx->current_trace_id.c_str(),
       static_cast<void*>(target),
       obs_source_name_or_unknown(target),
       obs_source_id_or_unknown(target),
       post.lines.size(),
       post.lines.empty() ? "" : post.lines.front().c_str(),
       obs_source_get_width(target),
       obs_source_get_height(target));
  ctx->shared_state_version = overlay_state_set_effective_font_size(render_font_size);
  std::vector<std::string> seg_ids = ctx ? ctx->current_segment_ids : std::vector<std::string>{};
  std::vector<std::string> seg_texts = ctx ? ctx->current_segments : std::vector<std::string>{};
  if (seg_ids.size() != seg_texts.size()) {
    seg_ids.clear();
    seg_texts.clear();
  }
  if (seg_ids.empty()) {
    seg_texts = post.lines;
    seg_ids.resize(seg_texts.size());
    for (size_t i = 0; i < seg_ids.size(); ++i) seg_ids[i] = "line-" + std::to_string(i);
  }
  auto spans = ctx ? ctx->current_spans : std::vector<OverlayRenderedSpan>{};
  if (spans.empty()) {
    spans = pipeline::compute_rendered_spans(visible_text, seg_ids, seg_texts);
  }
  if (!visible_text.empty()) {
    const std::string first = layout::normalize_label_token(layout::split_lines(visible_text).front());
    if (first == "mic" || first == "desktop") {
      blog(LOG_INFO, "what_overlay: body_leading_label_detected first='%s' header='%s' cfg_header='%s' text='%s'",
           first.c_str(), header.c_str(), ctx->config.header.c_str(), visible_text.c_str());
    }
  }
  overlay_state_set_rendered_output(visible_text, seg_ids, seg_texts, spans);
}

static void update_header_source(OverlaySource* ctx, const std::string& header) {
  if (!ctx) return;
  obs_source_t* target = header_update_source(ctx);
  const std::string requested_header = pipeline::resolve_header_update_text(ctx->config.header, header);
  if (!target) {
    if (!requested_header.empty()) {
      blog(LOG_WARNING, "what_overlay: header_source_missing src='%s' seq=%d trace='%s' header='%s'",
           source_label(ctx), ctx->current_seq, ctx->current_trace_id.c_str(), requested_header.c_str());
    }
    return;
  }
  const std::string raw_header = requested_header;
  if (raw_header.empty()) {
    obs_data_t* settings = obs_source_get_settings(target);
    obs_data_set_string(settings, "text", "");
    obs_source_update(target, settings);
    obs_data_release(settings);
    return;
  }
  auto to_upper = [](std::string value) {
    for (char& c : value) {
      c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }
    return value;
  };
  std::string text = ctx->config.uppercase ? to_upper(raw_header) : raw_header;
  const int content_w = content_width_px(ctx);
  const int content_h = content_height_px(ctx);
  const int label_h = std::max(
      12,
      layout::compute_label_height_px(ctx->config.font_size_px, raw_header));
  const bool target_is_header_source = (target == ctx->header_source);
  const uint32_t header_color = (ctx->text_color & 0x00FFFFFFu) | 0xFF000000u;
  const int header_units = std::max(
      8,
      label_font_units_for_header(ctx, raw_header));
  auto apply_header_settings = [&](bool use_extents) {
    obs_data_t* settings = obs_source_get_settings(target);
    obs_data_set_bool(settings, "from_file", false);
    obs_data_set_bool(settings, "word_wrap", false);
    obs_data_set_int(settings, "custom_width", use_extents ? content_w : 0);
    obs_data_set_bool(settings, "extents", use_extents);
    obs_data_set_int(settings, "extents_cx", use_extents ? content_w : 0);
    obs_data_set_int(settings, "extents_cy", use_extents ? content_h : 0);
    obs_data_set_int(settings, "color1", header_color);
    obs_data_set_int(settings, "color2", header_color);
    obs_data_set_string(settings, "align", "left");
    obs_data_set_string(settings, "text", text.c_str());
    obs_data_t* font = obs_data_create();
    obs_data_set_string(font, "face", ctx->config.font_family.c_str());
    obs_data_set_int(font, "size", header_units);
    obs_data_set_int(font, "flags", 0);
    obs_data_set_string(font, "style", "");
    obs_data_set_obj(settings, "font", font);
    obs_data_release(font);
    obs_source_update(target, settings);
    obs_data_release(settings);
  };
  apply_header_settings(target_is_header_source);
  const uint32_t hw = obs_source_get_width(target);
  const uint32_t hh = obs_source_get_height(target);
  uint32_t final_hw = hw;
  uint32_t final_hh = hh;
  if (target_is_header_source && !text.empty() && (hw == 0 || hh == 0)) {
    apply_header_settings(false);
    final_hw = obs_source_get_width(target);
    final_hh = obs_source_get_height(target);
    blog(LOG_INFO,
         "what_overlay: header_source_retry_intrinsic src='%s' seq=%d trace='%s' header='%s' before=%ux%u after=%ux%u",
         source_label(ctx),
         ctx->current_seq,
         ctx->current_trace_id.c_str(),
         text.c_str(),
         hw,
         hh,
         final_hw,
         final_hh);
  }
  blog(LOG_INFO, "what_overlay: header_source_updated src='%s' seq=%d trace='%s' header='%s' units=%d active='%s' target=%s ptr=%p name='%s' id='%s' src=%ux%u content_w=%d label_h=%d",
       source_label(ctx), ctx->current_seq, ctx->current_trace_id.c_str(),
       text.c_str(),
       header_units,
       active_header_text(ctx).c_str(),
       (target == ctx->overflow_source) ? "overflow_source" :
       (target == ctx->text_enter) ? "text_enter" :
       (target == ctx->header_source) ? "header_source" :
       (target == ctx->text_prev) ? "text_prev" : "unknown",
       static_cast<void*>(target),
       obs_source_name_or_unknown(target),
       obs_source_id_or_unknown(target),
       final_hw,
       final_hh,
       content_w,
       label_h);
}

static void set_text_source_alpha(OverlaySource* ctx, obs_source_t* target, float alpha01) {
  if (!ctx || !target) return;
  uint8_t base_a = static_cast<uint8_t>((ctx->text_color >> 24) & 0xFF);
  if (target == ctx->header_source || target == ctx->text_enter || target == ctx->overflow_source) {
    base_a = 0xFF;
  }
  const uint8_t r = static_cast<uint8_t>((ctx->text_color >> 16) & 0xFF);
  const uint8_t g = static_cast<uint8_t>((ctx->text_color >> 8) & 0xFF);
  const uint8_t b = static_cast<uint8_t>(ctx->text_color & 0xFF);
  const float clamped = std::max(0.0f, std::min(1.0f, alpha01));
  const uint8_t a = static_cast<uint8_t>(std::lround(static_cast<float>(base_a) * clamped));
  const uint32_t color = (static_cast<uint32_t>(a) << 24) |
                         (static_cast<uint32_t>(r) << 16) |
                         (static_cast<uint32_t>(g) << 8) |
                         static_cast<uint32_t>(b);
  obs_data_t* settings = obs_source_get_settings(target);
  obs_data_set_int(settings, "color1", color);
  obs_data_set_int(settings, "color2", color);
  obs_source_update(target, settings);
  obs_data_release(settings);
}

static void overlay_start_delay_worker(OverlaySource* ctx) {
  if (!ctx) return;
  ctx->delay_worker = std::thread([ctx]() {
    while (ctx->alive) {
      int delay_seconds = 0;
      std::string control_url;
      {
        std::unique_lock<std::mutex> lock(ctx->delay_mutex);
        ctx->delay_cv.wait(lock, [ctx]() {
          return ctx->delay_worker_stop || ctx->delay_dirty;
        });
        if (ctx->delay_worker_stop) break;
        delay_seconds = ctx->delay_target_seconds;
        control_url = ctx->delay_target_control_url;
        ctx->delay_dirty = false;
      }

      const bool posted = pipeline::post_publish_delay(control_url, delay_seconds);
      const int readback = pipeline::get_publish_delay_readback(control_url);
      std::string delay_text;
      if (readback >= 0) {
        delay_text = "API delay readback: " + std::to_string(readback) + "s";
      } else {
        delay_text =
            posted ? "API delay readback: pending/unavailable" : "API delay readback: update failed";
      }
      {
        std::lock_guard<std::mutex> lock(ctx->delay_mutex);
        ctx->delay_readback = delay_text;
      }
      ctx->shared_state_version = overlay_state_set_delay_readback(delay_text);
    }
  });
}

static void overlay_stop_delay_worker(OverlaySource* ctx) {
  if (!ctx) return;
  {
    std::lock_guard<std::mutex> lock(ctx->delay_mutex);
    ctx->delay_worker_stop = true;
  }
  ctx->delay_cv.notify_one();
  if (ctx->delay_worker.joinable()) {
    ctx->delay_worker.join();
  }
}

static void overlay_request_delay_sync(OverlaySource* ctx) {
  if (!ctx) return;
  {
    std::lock_guard<std::mutex> lock(ctx->delay_mutex);
    ctx->delay_target_seconds = ctx->config.delay_seconds;
    ctx->delay_target_control_url = ctx->config.control_url;
    ctx->delay_dirty = true;
  }
  ctx->delay_cv.notify_one();
}

static void mark_private_source_live(obs_source_t* source) {
  if (!source) return;
  obs_source_inc_active(source);
  obs_source_inc_showing(source);
}

static void unmark_private_source_live(obs_source_t* source) {
  if (!source) return;
  obs_source_dec_showing(source);
  obs_source_dec_active(source);
}

}  // namespace

static const char* overlay_get_name(void* /*unused*/) {
  return "What Captions";
}

static void* overlay_create(obs_data_t* settings, obs_source_t* source) {
  auto* ctx = new OverlaySource();
  blog(LOG_INFO, "what_overlay: plugin build stamp %s", kOverlayBuildStamp);
  ctx->self_source = source;
  const std::string source_name = source && obs_source_get_name(source)
                                      ? std::string(obs_source_get_name(source))
                                      : std::string("What Captions");
  ctx->source_name = source_name;
  const std::string header_name = source_name + " Header";
  const OverlayStateSnapshot initial_state = overlay_state_snapshot();
  ctx->config = initial_state.config;
  ctx->delay_readback = initial_state.delay_readback;
  ctx->shared_state_version = initial_state.version;
  auto create_private_text_source = [&](const char* source_id, const char* name) -> obs_source_t* {
    obs_data_t* source_settings = obs_data_create();
    obs_data_set_bool(source_settings, "from_file", false);
    obs_data_set_bool(source_settings, "word_wrap", false);
    obs_data_set_int(source_settings, "custom_width", 0);
    obs_data_set_bool(source_settings, "extents", false);
    obs_data_set_string(source_settings, "text", "");
    obs_source_t* created = obs_source_create_private(source_id, name, source_settings);
    obs_data_release(source_settings);
    return created;
  };

  ctx->text_source =
      create_private_text_source("text_ft2_source", "What Captions Text");
  ctx->text_prev =
      create_private_text_source("text_ft2_source", "What Captions Text Prev");
  ctx->text_enter =
      create_private_text_source("text_ft2_source", "What Captions Text Enter");
  ctx->header_source =
      create_private_text_source("text_ft2_source", header_name.c_str());
  ctx->overflow_source =
      create_private_text_source("text_ft2_source", "What Captions Overflow");
  if (!ctx->text_source) {
    ctx->text_source =
        create_private_text_source("text_gdiplus", "What Captions Text");
    ctx->text_prev =
        create_private_text_source("text_gdiplus", "What Captions Text Prev");
    ctx->text_enter =
        create_private_text_source("text_gdiplus", "What Captions Text Enter");
    ctx->header_source =
        create_private_text_source("text_gdiplus", header_name.c_str());
    ctx->overflow_source =
        create_private_text_source("text_gdiplus", "What Captions Overflow");
  }
  if (!ctx->header_source) {
    ctx->header_source =
        create_private_text_source("text_gdiplus", header_name.c_str());
  }
  mark_private_source_live(ctx->text_source);
  mark_private_source_live(ctx->text_prev);
  mark_private_source_live(ctx->text_enter);
  mark_private_source_live(ctx->header_source);
  mark_private_source_live(ctx->overflow_source);
  blog(LOG_INFO, "what_overlay: source_handles source='%s' text=%s prev=%s enter=%s header=%s overflow=%s",
       source_label(ctx),
       ctx->text_source ? "ok" : "null",
       ctx->text_prev ? "ok" : "null",
       ctx->text_enter ? "ok" : "null",
       ctx->header_source ? "ok" : "null",
       ctx->overflow_source ? "ok" : "null");
  blog(LOG_INFO, "what_overlay: source_ptrs source='%s' text=%p prev=%p enter=%p header=%p overflow=%p",
       source_label(ctx),
       static_cast<void*>(ctx->text_source),
       static_cast<void*>(ctx->text_prev),
       static_cast<void*>(ctx->text_enter),
       static_cast<void*>(ctx->header_source),
       static_cast<void*>(ctx->overflow_source));
  if (ctx->overflow_source) {
    obs_data_t* marker_settings = obs_source_get_settings(ctx->overflow_source);
    obs_data_set_string(marker_settings, "text", "...");
    obs_data_set_string(marker_settings, "align", "right");
    obs_data_set_bool(marker_settings, "word_wrap", false);
    obs_data_set_int(marker_settings, "custom_width", 0);
    obs_data_set_bool(marker_settings, "extents", false);
    obs_source_update(ctx->overflow_source, marker_settings);
    obs_data_release(marker_settings);
  }
  ctx->client.set_url(ctx->config.url);
  overlay_start_delay_worker(ctx);
  ctx->client.set_on_text([ctx](const std::string& payload) {
    if (!ctx || !ctx->alive) return;
    // Per-source stream filter: when set, this source renders only the matching stream.
    if (!ctx->config.stream.empty()) {
      const std::string src = pipeline::json_get_string(payload, "input_source_id");
      const std::string cid = pipeline::json_get_string(payload, "client_id");
      if (!pipeline::payload_stream_matches(src, cid, ctx->config.stream)) return;
    }
    const std::string payload_trace_id = pipeline::json_get_string(payload, "trace_id");
    // Live rendering should use bounded body payload (`text`/`lines`), not
    // cumulative transcript history (`fullText`), to avoid repeated large
    // payload churn and lag spikes.
    std::string text = pipeline::json_get_string(payload, "text");
    if (text.empty()) text = pipeline::json_get_string(payload, "fullText");
    const bool has_header_field = pipeline::json_has_key(payload, "header");
    const std::string header = pipeline::json_get_string(payload, "header");
    const std::vector<std::string> lines = pipeline::json_get_string_array(payload, "lines");
    pipeline::IngestRejectReason reject_reason = pipeline::IngestRejectReason::kNone;
    const auto payload_decision = pipeline::adapt_client_payload_decision(
        ctx->config.test_stream,
        payload_trace_id,
        !lines.empty(),
        text,
        header);
    reject_reason = payload_decision.reason;
    if (!payload_decision.accepted) {
      blog(LOG_INFO,
           "what_overlay: payload_ignored src='%s' seq=%d trace='%s' reason='%s'",
           source_label(ctx),
           pipeline::json_get_int(payload, "seq", -1),
           payload_trace_id.c_str(),
           pipeline::reject_reason_cstr(reject_reason));
      return;
    }
    const std::vector<pipeline::JsonSegment> segments = pipeline::json_get_segments(payload, "segments");
    const std::vector<pipeline::JsonSegmentSpan> segment_spans =
        pipeline::json_get_segment_spans(payload, "segmentSpans");
    const std::string transition = pipeline::json_get_string(payload, "transition");
    const std::string enter_line = pipeline::json_get_string(payload, "enterLine");
    const std::string animation_mode = pipeline::json_get_string(payload, "animationMode");
    const int payload_width = pipeline::json_get_int_loose(payload, "width", -1);
    const int payload_height = pipeline::json_get_int_loose(payload, "height", -1);
    const int payload_padding = pipeline::json_get_int_loose(payload, "padding", -1);
    const int payload_seq = pipeline::json_get_int(payload, "seq", -1);
    const double payload_font_size = pipeline::json_get_double_loose(payload, "fontSize", -1.0);
    blog(LOG_INFO,
         "what_overlay: payload_ingest src='%s' seq=%d trace='%s' lines_n=%zu text_len=%zu header='%s' has_header=%s transition='%s' enter='%s'",
         source_label(ctx),
         payload_seq,
         payload_trace_id.c_str(),
         lines.size(),
         text.size(),
         header.c_str(),
         has_header_field ? "yes" : "no",
         transition.c_str(),
         enter_line.c_str());
    {
      std::lock_guard<std::mutex> lock(ctx->mutex);
      ctx->pending_text = text;
      ctx->pending_header = header;
      ctx->pending_has_header = has_header_field;
      ctx->pending_lines = lines;
      ctx->pending_segment_ids.clear();
      ctx->pending_segments.clear();
      for (const auto& seg : segments) {
        ctx->pending_segment_ids.push_back(seg.id);
        ctx->pending_segments.push_back(seg.text);
      }
      ctx->pending_spans = pipeline::to_rendered_spans(segment_spans);
      ctx->pending_has_lines = !lines.empty();
      ctx->pending_transition = transition;
      ctx->pending_enter_line = enter_line;
      ctx->pending_animation_mode = animation_mode;
      ctx->pending_width_px = payload_width;
      ctx->pending_height_px = payload_height;
      ctx->pending_padding_px = payload_padding;
      ctx->pending_seq = payload_seq;
      ctx->pending_trace_id = payload_trace_id;
      ctx->pending_font_size_px = payload_font_size;
      ctx->pending_has_geometry =
          (payload_width > 0) || (payload_height > 0) || (payload_padding >= 0) || (payload_font_size > 0.0);
      ctx->has_pending = true;
    }
    obs_queue_task(OBS_TASK_UI, overlay_apply_pending, ctx, false);
  });
  ctx->client.start();
  if (settings) {
    overlay_update(ctx, settings);
  }
  return ctx;
}

static void overlay_destroy(void* data) {
  auto* ctx = static_cast<OverlaySource*>(data);
  if (ctx) {
    ctx->alive = false;
    overlay_stop_delay_worker(ctx);
    ctx->client.stop();
    if (ctx->text_source) {
      unmark_private_source_live(ctx->text_source);
      obs_source_release(ctx->text_source);
      ctx->text_source = nullptr;
    }
    if (ctx->text_prev) {
      unmark_private_source_live(ctx->text_prev);
      obs_source_release(ctx->text_prev);
      ctx->text_prev = nullptr;
    }
    if (ctx->text_enter) {
      unmark_private_source_live(ctx->text_enter);
      obs_source_release(ctx->text_enter);
      ctx->text_enter = nullptr;
    }
    if (ctx->header_source) {
      unmark_private_source_live(ctx->header_source);
      obs_source_release(ctx->header_source);
      ctx->header_source = nullptr;
    }
    if (ctx->overflow_source) {
      unmark_private_source_live(ctx->overflow_source);
      obs_source_release(ctx->overflow_source);
      ctx->overflow_source = nullptr;
    }
    ctx->self_source = nullptr;
  }
  delete ctx;
}

static void overlay_update(void* data, obs_data_t* settings) {
  auto* ctx = static_cast<OverlaySource*>(data);
  if (!ctx || !settings) return;
  const int previous_delay = ctx->config.delay_seconds;
  const std::string previous_service_url = ctx->config.url;
  const std::string previous_control_url = ctx->config.control_url;
  const bool previous_test_stream = ctx->config.test_stream;
  const int previous_max_segments = ctx->config.max_segments;
  const int previous_max_chars = ctx->config.max_chars;
  const int previous_width_px = ctx->config.width_px;
  const int previous_padding_x_px = ctx->config.padding_x_px;
  const double previous_font_size_px = ctx->config.font_size_px;
  const char* url = obs_data_get_string(settings, "url");
  const char* control_url = obs_data_get_string(settings, "control_url");
  const char* caption_stream = obs_data_get_string(settings, "caption_stream");
  const char* header = obs_data_get_string(settings, "header");
  const char* box_label = obs_data_get_string(settings, "box_label");
  const uint32_t text_color_int = static_cast<uint32_t>(obs_data_get_int(settings, "text_color"));
  const char* text_color = obs_data_get_string(settings, "text_color");
  const uint32_t bg_color_int = static_cast<uint32_t>(obs_data_get_int(settings, "bg_color"));
  const char* bg_color = obs_data_get_string(settings, "bg_color");
  const char* align = obs_data_get_string(settings, "align");
  const char* line_break_policy = obs_data_get_string(settings, "line_break_policy");
  const char* layout_engine = obs_data_get_string(settings, "layout_engine");
  const char* animation_mode = obs_data_get_string(settings, "animation_mode");
  obs_data_t* font_obj = obs_data_get_obj(settings, "font");

  if (url && *url) ctx->config.url = url;
  if (control_url && *control_url) ctx->config.control_url = control_url;
  // Caption-stream filter (empty = all streams). Assign unconditionally so it can clear.
  ctx->config.stream = caption_stream ? caption_stream : "";
  bool header_overridden_from_settings = false;
  // `box_label` is canonical and must be able to clear to empty when labels
  // are disabled. Legacy `header` is only used when `box_label` is absent.
  if (obs_data_has_user_value(settings, "box_label")) {
    ctx->config.header = box_label ? box_label : "";
    header_overridden_from_settings = true;
  } else if (obs_data_has_user_value(settings, "header")) {
    ctx->config.header = header ? header : "";
    header_overridden_from_settings = true;
  }
  // If panel/source settings explicitly changed the header, apply it
  // immediately even during active payload flow so Box Labels toggles always
  // take effect after test-stream sessions.
  if (header_overridden_from_settings ||
      (ctx->current_text.empty() && ctx->current_lines.empty())) {
    ctx->current_header = ctx->config.header;
  }
  if (text_color && *text_color) ctx->config.text_color = text_color;
  if (bg_color_int != 0) {
    ctx->config.bg_color = "";
    ctx->bg_color = bg_color_int;
  } else if (bg_color && *bg_color) {
    ctx->config.bg_color = bg_color;
    ctx->bg_color = parse_bg_color_for_render(bg_color);
  } else {
    ctx->bg_color = 0x00000000;
  }
  if (align && *align) ctx->config.align = align;
  if (line_break_policy && *line_break_policy) {
    ctx->config.line_break_policy = line_break_policy;
  }
  if (layout_engine && *layout_engine) ctx->config.layout_engine = layout_engine;
  if (animation_mode && *animation_mode) ctx->config.animation_mode = animation_mode;
  if (font_obj) {
    const char* face = obs_data_get_string(font_obj, "face");
    if (face && *face) ctx->config.font_family = face;
    obs_data_release(font_obj);
  }

  const int max_segments = static_cast<int>(obs_data_get_int(settings, "max_segments"));
  const int max_chars = static_cast<int>(obs_data_get_int(settings, "max_chars"));
  const double font_size = obs_data_get_double(settings, "font_size");
  const bool uppercase = obs_data_get_bool(settings, "uppercase");
  const bool auto_shrink_to_fit = obs_data_get_bool(settings, "auto_shrink_to_fit");
  const bool no_word_split = obs_data_has_user_value(settings, "no_word_split")
                                 ? obs_data_get_bool(settings, "no_word_split")
                                 : true;
  const bool test_stream_from_settings = obs_data_get_bool(settings, "test_stream");
  const int delay_seconds = static_cast<int>(obs_data_get_int(settings, "delay_seconds"));
  const int width = static_cast<int>(obs_data_get_int(settings, "width"));
  const int height = static_cast<int>(obs_data_get_int(settings, "height"));
  const int pad_x = static_cast<int>(obs_data_get_int(settings, "pad_x"));
  const int pad_y = static_cast<int>(obs_data_get_int(settings, "pad_y"));
  const bool outline_enabled = obs_data_get_bool(settings, "outline_enabled");
  const int outline_thickness_px = static_cast<int>(obs_data_get_int(settings, "outline_thickness_px"));

  if (max_segments > 0) ctx->config.max_segments = max_segments;
  if (max_chars > 0) ctx->config.max_chars = max_chars;
  if (font_size > 0.0) ctx->config.font_size_px = font_size;
  if (width > 0) ctx->config.width_px = width;
  if (height > 0) ctx->config.height_px = height;
  if (pad_x >= 0) ctx->config.padding_x_px = pad_x;
  if (pad_y >= 0) ctx->config.padding_y_px = pad_y;
  ctx->config.padding_x_px =
      std::max(0, std::min(ctx->config.padding_x_px, std::max(0, (ctx->config.width_px / 2) - 1)));
  ctx->config.padding_y_px =
      std::max(0, std::min(ctx->config.padding_y_px, std::max(0, (ctx->config.height_px / 2) - 1)));
  ctx->config.uppercase = uppercase;
  // Deprecated: preserve config bit for UI compatibility, but never use this
  // to auto-scale font on geometry changes.
  ctx->config.auto_shrink_to_fit = auto_shrink_to_fit;
  ctx->config.no_word_split = no_word_split;
  ctx->config.outline_enabled = outline_enabled;
  if (outline_thickness_px > 0) {
    ctx->config.outline_thickness_px = std::max(1, std::min(24, outline_thickness_px));
  }
  // Test stream should follow source settings updates (panel/runtime apply).
  bool test_stream = test_stream_from_settings;
  if (!ctx->initialized_test_stream_default) {
    test_stream = false;
    ctx->initialized_test_stream_default = true;
    obs_data_set_bool(settings, "test_stream", false);
  }
  ctx->config.test_stream = test_stream;
  ctx->config.delay_seconds = std::max(0, delay_seconds);

  if (text_color_int != 0) {
    ctx->text_color = text_color_int;
  } else if (text_color && *text_color) {
    ctx->text_color = parse_text_color_for_obs(text_color);
  } else {
    ctx->text_color = 0xFFFFFFFF;
  }
#ifdef what_overlay_debug
  blog(LOG_INFO, "what_overlay: text_color=0x%08X (raw=%lld, str=%s, font=%s)",
       ctx->text_color, static_cast<long long>(text_color_int),
       text_color && *text_color ? text_color : "(none)",
       ctx->config.font_family.empty() ? "(default)" : ctx->config.font_family.c_str());
#endif

  if (!ctx->current_lines.empty()) {
    update_text_source_lines(ctx, ctx->text_source, ctx->current_lines, ctx->current_header);
  } else {
    update_text_source(ctx, ctx->text_source, ctx->current_text, ctx->current_header);
  }
  update_header_source(ctx, ctx->current_header);

  std::string delay_readback_text;
  {
    std::lock_guard<std::mutex> lock(ctx->delay_mutex);
    delay_readback_text = ctx->delay_readback;
  }
  obs_data_set_string(settings, "delay_readback", delay_readback_text.c_str());

  ctx->shared_state_version = overlay_state_set_config(ctx->config);
  ctx->shared_state_version = overlay_state_set_delay_readback(delay_readback_text);

  if (ctx->config.delay_seconds != previous_delay ||
      ctx->config.control_url != previous_control_url) {
    overlay_request_delay_sync(ctx);
  }

  if (ctx->config.url != previous_service_url) {
    blog(LOG_INFO, "what_overlay: source_url_changed src='%s' old='%s' new='%s'",
         source_label(ctx), previous_service_url.c_str(), ctx->config.url.c_str());
    ctx->client.stop();
    ctx->client.set_url(ctx->config.url);
    ctx->client.start();
  }
  const bool test_stream_constraints_changed =
      (ctx->config.max_segments != previous_max_segments) ||
      (ctx->config.max_chars != previous_max_chars) ||
      (ctx->config.width_px != previous_width_px) ||
      (ctx->config.padding_x_px != previous_padding_x_px) ||
      (ctx->config.font_size_px != previous_font_size_px);
  if (ctx->config.test_stream != previous_test_stream ||
      (ctx->config.test_stream && test_stream_constraints_changed) ||
      ctx->test_stream_last_sent != ctx->config.test_stream) {
    blog(LOG_INFO, "what_overlay: test_stream_state src='%s' desired=%s last_sent=%s url=%s",
         source_label(ctx),
         ctx->config.test_stream ? "true" : "false",
         ctx->test_stream_last_sent ? "true" : "false",
         ctx->config.url.c_str());
    blog(LOG_INFO,
         "what_overlay: post_test_stream_toggle target=%s enabled=%s lines_limit=%d max_chars=%d max_segments=%d width_px=%d padding_px=%d font_ui=%.2f",
         ctx->config.url.c_str(),
         ctx->config.test_stream ? "true" : "false",
         ctx->config.max_segments,
         ctx->config.max_chars,
         ctx->config.max_segments,
         ctx->config.width_px,
         ctx->config.padding_x_px,
         ctx->config.font_size_px);
    const bool ok = pipeline::post_test_stream_toggle(
        ctx->config.url,
        pipeline::TestStreamToggleRequest{
            ctx->config.test_stream,
            ctx->config.max_segments,
            ctx->config.max_chars,
            ctx->config.max_segments,
            ctx->config.width_px,
            ctx->config.padding_x_px,
            ctx->config.font_size_px});
    if (!ok) {
      blog(LOG_WARNING, "what_overlay: failed to toggle test stream at %s", ctx->config.url.c_str());
      // Keep this mismatched so overlay_tick retries until successful.
      ctx->test_stream_last_sent = !ctx->config.test_stream;
    } else {
      ctx->test_stream_last_sent = ctx->config.test_stream;
    }
  }
}

static void overlay_sync_from_shared_state(OverlaySource* ctx) {
  if (!ctx) return;
  const OverlayStateSnapshot snapshot = overlay_state_snapshot();
  if (snapshot.version == ctx->shared_state_version) return;
  // Do not overwrite per-source config (URL/style) from global shared state.
  // Multiple What Captions sources must keep independent URLs/settings.
  {
    std::lock_guard<std::mutex> lock(ctx->delay_mutex);
    ctx->delay_readback = snapshot.delay_readback;
  }
  ctx->shared_state_version = snapshot.version;
}

static obs_properties_t* overlay_properties(void* /*data*/) {
  obs_properties_t* props = obs_properties_create();
  obs_properties_add_text(
      props, "captions_hint",
      "Tip: the What Captions dock's Mic / Desktop box checkboxes create and configure "
      "these sources for you. Adding one by hand? Just pick its Caption stream below.",
      OBS_TEXT_INFO);
  obs_properties_add_text(props, "url", "Overlay URL", OBS_TEXT_DEFAULT);
  obs_properties_add_text(props, "control_url", "Control API URL", OBS_TEXT_DEFAULT);
  // Which caption lane this source renders. This used to be a free-text field, so
  // running separate mic and desktop boxes meant knowing to type the lane id by hand --
  // the ids are the `input_source_id` the service stamps on each event ("mic",
  // "desktop", "mixed"), which is not discoverable from the source dialog. Editable, so
  // a custom client_id still works for anyone routing extra streams.
  obs_property_t* stream_prop = obs_properties_add_list(
      props, "caption_stream", "Caption stream",
      OBS_COMBO_TYPE_EDITABLE, OBS_COMBO_FORMAT_STRING);
  obs_property_list_add_string(stream_prop, "All streams", "");
  obs_property_list_add_string(stream_prop, "Mic", "mic");
  obs_property_list_add_string(stream_prop, "Desktop / app audio", "desktop");
  obs_property_list_add_string(stream_prop, "Mixed (mic + desktop)", "mixed");
  obs_property_set_long_description(
      stream_prop,
      "Which transcription stream this box shows. Add one source set to Mic and another "
      "set to Desktop to caption them separately. Leave on All streams for a single box "
      "showing everything.");
  obs_properties_add_text(props, "header", "Header", OBS_TEXT_DEFAULT);
  obs_properties_add_int(props, "max_segments", "Max Segments", 1, 10, 1);
  obs_properties_add_int(props, "max_chars", "Max Chars", 50, 1000, 10);
  obs_property_t* font_size =
      obs_properties_add_float_slider(props, "font_size", "Font Size", 0.1, 40.0, 0.05);
  obs_property_float_set_suffix(font_size, "      ");
  obs_property_t* delay =
      obs_properties_add_int_slider(props, "delay_seconds", "Transcript Delay (seconds)", 0, 90, 1);
  obs_property_int_set_suffix(delay, "                  ");
  obs_property_t* delay_readback =
      obs_properties_add_text(props, "delay_readback", "Delay Readback", OBS_TEXT_INFO);
  obs_property_text_set_info_type(delay_readback, OBS_TEXT_INFO_NORMAL);
  obs_properties_add_bool(props, "uppercase", "Auto-capitalize (UPPERCASE)");
  obs_properties_add_bool(props, "auto_shrink_to_fit", "Auto-shrink text to fit box");
  obs_properties_add_bool(props, "no_word_split", "No Word Split (keep whole words)");
  obs_properties_add_bool(props, "test_stream", "Test Stream (plugin local)");
  obs_property_t* mode_prop =
      obs_properties_add_list(props, "animation_mode", "Animation Mode", OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_STRING);
  obs_property_list_add_string(mode_prop, "none", "none");
  obs_property_list_add_string(mode_prop, "token_fade", "token_fade");
  obs_property_list_add_string(mode_prop, "line_roll", "line_roll");
  obs_property_list_add_string(mode_prop, "hybrid", "hybrid");
  obs_property_t* layout_prop = obs_properties_add_list(
      props, "layout_engine", "Layout Engine", OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_STRING);
  obs_property_list_add_string(layout_prop, "legacy", "legacy");
  obs_property_list_add_string(layout_prop, "measured_v1", "measured_v1");
  obs_property_t* warning = obs_properties_add_text(
      props, "auto_shrink_warning",
      "Warning: auto-shrink can reduce legibility on small screens.", OBS_TEXT_INFO);
  obs_property_text_set_info_type(warning, OBS_TEXT_INFO_WARNING);
  obs_properties_add_color_alpha(props, "text_color", "Text Color");
  obs_properties_add_color_alpha(props, "bg_color", "Background Color");
  obs_properties_add_int(props, "width", "Box Width (px)", 100, 1920, 10);
  obs_properties_add_int(props, "height", "Box Height (px)", 60, 1080, 10);
  obs_properties_add_int(props, "pad_x", "Pad X (px)", 0, 2000, 1);
  obs_properties_add_int(props, "pad_y", "Pad Y (px)", 0, 2000, 1);
  obs_properties_add_bool(props, "outline_enabled", "Show Outline");
  obs_properties_add_int(props, "outline_thickness_px", "Outline Thickness (px)", 1, 24, 1);
  obs_property_t* align_prop =
      obs_properties_add_list(props, "align", "Align", OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_STRING);
  obs_property_list_add_string(align_prop, "left", "left");
  obs_property_list_add_string(align_prop, "center", "center");
  obs_property_list_add_string(align_prop, "right", "right");
  obs_properties_add_font(props, "font", "Font");
  return props;
}

static void overlay_defaults(obs_data_t* settings) {
  // The GUI's overlay server, not the raw what service. It keeps a word-wrapped window PER
  // stream, which is what lets a mic box and a desktop box fill independently -- the raw
  // :8765 feed has no per-stream windowing. 127.0.0.1 because that server runs wherever
  // the pipeline and OBS do.
  obs_data_set_default_string(settings, "url", "http://127.0.0.1:8790/events");
  obs_data_set_default_string(settings, "control_url", "http://127.0.0.1:8780");
  obs_data_set_default_string(settings, "header", "");
  obs_data_set_default_string(settings, "box_label", "");
  obs_data_set_default_int(settings, "max_segments", 3);
  obs_data_set_default_int(settings, "max_chars", 280);
  obs_data_set_default_double(settings, "font_size", 3.0);
  obs_data_set_default_int(settings, "delay_seconds", 0);
  obs_data_set_default_string(settings, "delay_readback", "API delay readback: unavailable");
  obs_data_set_default_bool(settings, "uppercase", false);
  obs_data_set_default_bool(settings, "auto_shrink_to_fit", false);
  obs_data_set_default_bool(settings, "no_word_split", true);
  obs_data_set_default_string(settings, "line_break_policy", "reflow_all");
  obs_data_set_default_bool(settings, "test_stream", false);
  obs_data_set_default_string(settings, "layout_engine", "legacy");
  obs_data_set_default_string(settings, "animation_mode", "none");
  obs_data_set_default_int(settings, "text_color", 0xFFFFFFFF);
  obs_data_set_default_int(settings, "bg_color", 0x00000000);
  obs_data_set_default_int(settings, "width", 640);
  obs_data_set_default_int(settings, "height", 140);
  obs_data_set_default_int(settings, "pad_x", 6);
  obs_data_set_default_int(settings, "pad_y", 4);
  obs_data_set_default_bool(settings, "outline_enabled", true);
  obs_data_set_default_int(settings, "outline_thickness_px", 3);
  obs_data_set_default_string(settings, "align", "left");
}

static void overlay_render(void* data, gs_effect_t* /*effect*/) {
  auto* ctx = static_cast<OverlaySource*>(data);
  if (!ctx || !ctx->text_source) return;
  const std::string active_header = active_header_text(ctx);
  const pipeline::RenderGeometry geometry = pipeline::adapt_render_geometry(ctx->config, active_header);
  const int top_extra = geometry.top_extra_px;
  const float box_y = geometry.box_y;
  const int outline_px = geometry.outline_px;
  const int top_pad = geometry.header_top_pad;
  if (debug_logging_enabled()) {
    char dbg[320] = {};
    const uint32_t tsw = ctx->text_source ? obs_source_get_width(ctx->text_source) : 0u;
    const uint32_t tsh = ctx->text_source ? obs_source_get_height(ctx->text_source) : 0u;
    const uint32_t tpw = ctx->text_prev ? obs_source_get_width(ctx->text_prev) : 0u;
    const uint32_t tph = ctx->text_prev ? obs_source_get_height(ctx->text_prev) : 0u;
    const uint32_t tew = ctx->text_enter ? obs_source_get_width(ctx->text_enter) : 0u;
    const uint32_t teh = ctx->text_enter ? obs_source_get_height(ctx->text_enter) : 0u;
    const uint32_t hsw = header_render_source(ctx) ? obs_source_get_width(header_render_source(ctx)) : 0u;
    const uint32_t hsh = header_render_source(ctx) ? obs_source_get_height(header_render_source(ctx)) : 0u;
    const int content_w = content_width_px(ctx);
    const int content_h = content_height_px(ctx);
    const std::string body_preview = source_text_preview(ctx->text_source);
    const std::string header_preview = source_text_preview(header_render_source(ctx));
    std::snprintf(dbg, sizeof(dbg),
                  "what_overlay: render_layout src='%s' seq=%d trace='%s' header='%s' top_extra=%d header_y=%d box_y=%.1f outline=%d h=%d header_units=%d header_src=%ux%u text=%ux%u prev=%ux%u enter=%ux%u body_id='%s' header_id='%s' body_preview='%s' header_preview='%s' content=%dx%d",
                  source_label(ctx), ctx->current_seq, ctx->current_trace_id.c_str(), active_header.c_str(),
                  top_extra, top_pad, box_y, outline_px, ctx->config.height_px, label_font_units(ctx),
                  hsw, hsh, tsw, tsh, tpw, tph, tew, teh,
                  obs_source_id_or_unknown(ctx->text_source),
                  obs_source_id_or_unknown(header_render_source(ctx)),
                  body_preview.c_str(), header_preview.c_str(), content_w, content_h);
    const std::string line = dbg;
    if (line != ctx->last_geometry_debug_line) {
      blog(LOG_INFO, "%s", line.c_str());
      ctx->last_geometry_debug_line = line;
    }
    const int slack_w = content_w - static_cast<int>(tsw);
    const int slack_h = content_h - static_cast<int>(tsh);
    char margin_dbg[320] = {};
    std::snprintf(
        margin_dbg,
        sizeof(margin_dbg),
        "what_overlay: margin_probe src='%s' seq=%d trace='%s' content=%dx%d text=%ux%u slack_w=%d slack_h=%d lines_n=%zu text_len=%zu",
        source_label(ctx),
        ctx->current_seq,
        ctx->current_trace_id.c_str(),
        content_w,
        content_h,
        tsw,
        tsh,
        slack_w,
        slack_h,
        ctx->current_lines.size(),
        ctx->current_text.size());
    const std::string margin_line = margin_dbg;
    const uint64_t now_ns = os_gettime_ns();
    const uint64_t interval_ns = 2ull * 1000ull * 1000ull * 1000ull;  // 2s keepalive log
    const bool should_log_margin =
        (margin_line != ctx->last_margin_probe_debug_line) ||
        (ctx->last_margin_probe_log_ns == 0) ||
        (now_ns - ctx->last_margin_probe_log_ns >= interval_ns);
    if (should_log_margin) {
      blog(LOG_INFO, "%s", margin_line.c_str());
      ctx->last_margin_probe_debug_line = margin_line;
      ctx->last_margin_probe_log_ns = now_ns;
    }
  }

  obs_source_t* header_src = header_render_source(ctx);
  if (header_src && !active_header.empty()) {
    // Header must remain visible regardless of prior transition alpha state on
    // shared private text sources (e.g. text_prev fallback path).
    set_text_source_alpha(ctx, header_src, 1.0f);
    const float header_x = geometry.header_x;
    const float header_y = geometry.header_y;
    gs_matrix_push();
    gs_matrix_translate3f(header_x, header_y, 0.0f);
    obs_source_video_render(header_src);
    gs_matrix_pop();
  }

  // Hard guard: never render body text layers when there is no computed body
  // content. This prevents stale internal text-source state from appearing in
  // the body region when labels are enabled.
  const bool has_body_content = !ctx->wrapped_text.empty() ||
                                !ctx->current_text.empty() ||
                                !ctx->current_lines.empty();

  if (ctx->config.outline_enabled && outline_px > 0) {
    gs_effect_t* solid = obs_get_base_effect(OBS_EFFECT_SOLID);
    if (solid) {
      struct vec4 color = {};
      vec4_from_rgba(&color, 0xFFFFFFFF);
      gs_eparam_t* color_param = gs_effect_get_param_by_name(solid, "color");
      gs_technique_t* tech = gs_effect_get_technique(solid, "Solid");
      gs_effect_set_vec4(color_param, &color);
      gs_technique_begin(tech);
      gs_technique_begin_pass(tech, 0);
      gs_matrix_push();
      gs_matrix_translate3f(0.0f, box_y, 0.0f);
      gs_draw_sprite(nullptr, 0, ctx->config.width_px, outline_px);
      gs_matrix_pop();
      gs_matrix_push();
      gs_matrix_translate3f(0.0f, box_y + static_cast<float>(ctx->config.height_px - outline_px), 0.0f);
      gs_draw_sprite(nullptr, 0, ctx->config.width_px, outline_px);
      gs_matrix_pop();
      gs_matrix_push();
      gs_matrix_translate3f(0.0f, box_y, 0.0f);
      gs_draw_sprite(nullptr, 0, outline_px, ctx->config.height_px);
      gs_matrix_pop();
      gs_matrix_push();
      gs_matrix_translate3f(static_cast<float>(ctx->config.width_px - outline_px), box_y, 0.0f);
      gs_draw_sprite(nullptr, 0, outline_px, ctx->config.height_px);
      gs_matrix_pop();
      gs_technique_end_pass(tech);
      gs_technique_end(tech);
    }
  }

  if (ctx->bg_color != 0x00000000) {
    gs_effect_t* solid = obs_get_base_effect(OBS_EFFECT_SOLID);
    if (solid) {
      struct vec4 color = {};
      vec4_from_rgba(&color, ctx->bg_color);
      gs_eparam_t* color_param = gs_effect_get_param_by_name(solid, "color");
      gs_technique_t* tech = gs_effect_get_technique(solid, "Solid");
      gs_effect_set_vec4(color_param, &color);
      gs_technique_begin(tech);
      gs_technique_begin_pass(tech, 0);
      gs_matrix_push();
      gs_matrix_translate3f(0.0f, box_y, 0.0f);
      gs_draw_sprite(0, 0, ctx->config.width_px, ctx->config.height_px);
      gs_matrix_pop();
      gs_technique_end_pass(tech);
      gs_technique_end(tech);
    }
  }

  const float pad_x = geometry.body_pad_x;
  const float pad_y = geometry.body_pad_y;
  if (!has_body_content) {
    return;
  }
  if (ctx->animating && ctx->anim_fade_only && ctx->text_prev) {
    gs_matrix_push();
    gs_matrix_translate3f(pad_x, pad_y, 0.0f);
    obs_source_video_render(ctx->text_prev);
    obs_source_video_render(ctx->text_source);
    gs_matrix_pop();
    return;
  }
  if (ctx->animating && ctx->text_prev && ctx->text_enter) {
    const float y = std::round(ctx->anim_offset);
    gs_matrix_push();
    gs_matrix_translate3f(pad_x, pad_y + (ctx->anim_shift_prev ? -y : 0.0f), 0.0f);
    obs_source_video_render(ctx->text_prev);
    gs_matrix_pop();

    gs_matrix_push();
    const float enter_start = ctx->anim_shift_prev ? ctx->line_height : (ctx->line_height * 2.0f);
    const float enter_y = enter_start - y;
    gs_matrix_translate3f(pad_x, pad_y + enter_y, 0.0f);
    obs_source_video_render(ctx->text_enter);
    gs_matrix_pop();
    return;
  }

  gs_matrix_push();
  gs_matrix_translate3f(pad_x, pad_y, 0.0f);
  obs_source_video_render(ctx->text_source);
  gs_matrix_pop();
  if (ctx->overflowed && !ctx->config.auto_shrink_to_fit && ctx->overflow_source) {
    obs_data_t* marker_settings = obs_source_get_settings(ctx->overflow_source);
    obs_data_set_string(marker_settings, "text", "...");
    obs_data_set_string(marker_settings, "align", "right");
    obs_data_set_int(marker_settings, "custom_width", 0);
    obs_data_set_bool(marker_settings, "extents", false);
    obs_data_set_int(marker_settings, "color1", ctx->text_color);
    obs_data_set_int(marker_settings, "color2", ctx->text_color);
    obs_data_t* font = obs_data_create();
    obs_data_set_string(font, "face", ctx->config.font_family.c_str());
    const int marker_font_units =
        static_cast<int>(std::lround(std::max(0.5, ctx->config.font_size_px * 0.7) * kObsFontScale));
    obs_data_set_int(font, "size", marker_font_units);
    obs_data_set_int(font, "flags", 0);
    obs_data_set_string(font, "style", "");
    obs_data_set_obj(marker_settings, "font", font);
    obs_data_release(font);
    obs_source_update(ctx->overflow_source, marker_settings);
    obs_data_release(marker_settings);

    gs_matrix_push();
    gs_matrix_translate3f(geometry.overflow_x, geometry.overflow_y, 0.0f);
    obs_source_video_render(ctx->overflow_source);
    gs_matrix_pop();
  }
}

static void overlay_tick(void* data, float seconds) {
  auto* ctx = static_cast<OverlaySource*>(data);
  if (!ctx) return;
  overlay_sync_from_shared_state(ctx);
  if (ctx->test_stream_last_sent != ctx->config.test_stream) {
    const uint64_t now = os_gettime_ns();
    if (now - ctx->test_stream_retry_ns >= 1000000000ULL) {
      const bool ok = pipeline::post_test_stream_toggle(
          ctx->config.url,
          pipeline::TestStreamToggleRequest{
              ctx->config.test_stream,
              ctx->config.max_segments,
              ctx->config.max_chars,
              ctx->config.max_segments,
              ctx->config.width_px,
              ctx->config.padding_x_px,
              ctx->config.font_size_px});
      if (ok) {
        ctx->test_stream_last_sent = ctx->config.test_stream;
      }
      ctx->test_stream_retry_ns = now;
    }
  }
  if (!ctx->animating) return;
  const double elapsed = static_cast<double>(os_gettime_ns() - ctx->anim_start_ns) / 1e9;
  if (elapsed >= ctx->anim_duration_s) {
    if (ctx->anim_fade_only) {
      set_text_source_alpha(ctx, ctx->text_prev, 0.0f);
      set_text_source_alpha(ctx, ctx->text_source, 1.0f);
    }
    ctx->animating = false;
    ctx->anim_fade_only = false;
    ctx->anim_offset = 0.0f;
    if (ctx->has_pending) {
      obs_queue_task(OBS_TASK_UI, overlay_apply_pending, ctx, false);
    }
    return;
  }
  const float t = static_cast<float>(elapsed / ctx->anim_duration_s);
  if (ctx->anim_fade_only) {
    set_text_source_alpha(ctx, ctx->text_prev, 1.0f - t);
    set_text_source_alpha(ctx, ctx->text_source, t);
    ctx->anim_offset = 0.0f;
  } else {
    ctx->anim_offset = ctx->line_height * t;
  }
  (void)seconds;
}

static uint32_t overlay_get_width(void* data) {
  auto* ctx = static_cast<OverlaySource*>(data);
  if (!ctx) return 0;
  return static_cast<uint32_t>(ctx->config.width_px);
}

static uint32_t overlay_get_height(void* data) {
  auto* ctx = static_cast<OverlaySource*>(data);
  if (!ctx) return 0;
  return static_cast<uint32_t>(ctx->config.height_px + top_extra_px(ctx));
}

static obs_source_info make_overlay_info() {
  obs_source_info info = {};
  info.id = "what_captions_source";
  info.type = OBS_SOURCE_TYPE_INPUT;
  info.output_flags = OBS_SOURCE_VIDEO | OBS_SOURCE_CUSTOM_DRAW;
  info.get_name = overlay_get_name;
  info.create = overlay_create;
  info.destroy = overlay_destroy;
  info.update = overlay_update;
  info.get_properties = overlay_properties;
  info.get_defaults = overlay_defaults;
  info.video_render = overlay_render;
  info.video_tick = overlay_tick;
  info.get_width = overlay_get_width;
  info.get_height = overlay_get_height;
  return info;
}

static obs_source_info overlay_info = make_overlay_info();

const obs_source_info* get_overlay_source_info() {
  return &overlay_info;
}

static void overlay_apply_pending(void* param) {
  auto* ctx = static_cast<OverlaySource*>(param);
  if (!ctx || !ctx->alive) return;
  if (!ctx->has_pending) return;
  // Don't swap source buffers while an animation is running; apply latest
  // pending payload right after the current transition finishes.
  if (ctx->animating) return;
  std::string text;
  std::string header;
  std::vector<std::string> lines;
  std::vector<std::string> segment_ids;
  std::vector<std::string> segments;
  std::vector<OverlayRenderedSpan> spans;
  bool has_payload_header = false;
  bool has_lines = false;
  std::string transition_hint;
  std::string enter_line_hint;
  std::string animation_mode_hint;
  int pending_width_px = -1;
  int pending_height_px = -1;
  int pending_padding_px = -1;
  int pending_seq = -1;
  std::string pending_trace_id;
  double pending_font_size_px = -1.0;
  bool has_geometry = false;
  {
    std::lock_guard<std::mutex> lock(ctx->mutex);
    text = ctx->pending_text;
    header = ctx->pending_header;
    has_payload_header = ctx->pending_has_header;
    lines = ctx->pending_lines;
    segment_ids = ctx->pending_segment_ids;
    segments = ctx->pending_segments;
    spans = ctx->pending_spans;
    has_lines = ctx->pending_has_lines;
    transition_hint = ctx->pending_transition;
    enter_line_hint = ctx->pending_enter_line;
    animation_mode_hint = ctx->pending_animation_mode;
    pending_width_px = ctx->pending_width_px;
    pending_height_px = ctx->pending_height_px;
    pending_padding_px = ctx->pending_padding_px;
    pending_seq = ctx->pending_seq;
    pending_trace_id = ctx->pending_trace_id;
    pending_font_size_px = ctx->pending_font_size_px;
    has_geometry = ctx->pending_has_geometry;
    ctx->pending_has_header = false;
    ctx->pending_has_lines = false;
    ctx->pending_segment_ids.clear();
    ctx->pending_segments.clear();
    ctx->pending_spans.clear();
    ctx->pending_transition.clear();
    ctx->pending_enter_line.clear();
    ctx->pending_animation_mode.clear();
    ctx->pending_width_px = -1;
    ctx->pending_height_px = -1;
    ctx->pending_padding_px = -1;
    ctx->pending_seq = -1;
    ctx->pending_trace_id.clear();
    ctx->pending_font_size_px = -1.0;
    ctx->pending_has_geometry = false;
    ctx->has_pending = false;
  }
  ctx->current_seq = pending_seq;
  ctx->current_trace_id = pending_trace_id;
  const std::string payload_header = header;
  const auto pending_decision = pipeline::adapt_pending_payload_decision(
      ctx->config,
      ctx->current_header,
      payload_header,
      has_payload_header,
      has_lines,
      text);
  const std::string effective_header = pending_decision.effective_header;
  if (!pending_decision.accepted) {
    blog(LOG_INFO, "what_overlay: apply_pending_ignored src='%s' seq=%d trace='%s' reason='%s'",
         source_label(ctx), pending_seq, pending_trace_id.c_str(),
         pipeline::reject_reason_cstr(pending_decision.reason));
    return;
  }
  blog(LOG_INFO, "what_overlay: apply_pending src='%s' seq=%d trace='%s' has_lines=%s lines_n=%zu text_len=%zu header='%s' cfg_header='%s'",
       source_label(ctx),
       pending_seq,
       pending_trace_id.c_str(),
       has_lines ? "yes" : "no",
       lines.size(),
       text.size(),
       effective_header.c_str(),
       ctx->config.header.c_str());
  bool geometry_changed = false;
  // Stream payload geometry remains informational for plugin mode.
  // OBS source settings / panel scene-link behavior remain authoritative.
  (void)has_geometry;
  const uint32_t output_w = ctx->self_source ? obs_source_get_width(ctx->self_source) : 0;
  const uint32_t output_h = ctx->self_source ? obs_source_get_height(ctx->self_source) : 0;
  char line[560] = {};
  std::snprintf(
      line, sizeof(line),
      "what_overlay: geometry has_payload=%s apply=ignored payload(w=%d h=%d pad=%d fs=%.2f) config(w=%d h=%d pad=(%d,%d) fs=%.2f) output(w=%u h=%u) content(w=%d h=%d)",
      has_geometry ? "yes" : "no",
      pending_width_px, pending_height_px, pending_padding_px, pending_font_size_px,
      ctx->config.width_px, ctx->config.height_px, ctx->config.padding_x_px, ctx->config.padding_y_px,
      ctx->config.font_size_px, output_w, output_h, content_width_px(ctx), content_height_px(ctx));
  const std::string debug_line = line;
  if (debug_line != ctx->last_geometry_debug_line) {
    blog(LOG_INFO, "%s", debug_line.c_str());
    ctx->last_geometry_debug_line = debug_line;
  }
  if (has_lines) {
    const std::vector<std::string> prev_lines = ctx->current_lines;
    const std::string prev_header = ctx->current_header;
    (void)geometry_changed;
    ctx->current_lines = lines;
    if (!segment_ids.empty() && segment_ids.size() == segments.size()) {
      ctx->current_segment_ids = segment_ids;
      ctx->current_segments = segments;
      ctx->current_spans = spans;
    } else {
      ctx->current_segment_ids.clear();
      ctx->current_segments.clear();
      ctx->current_spans.clear();
    }
    ctx->current_text = layout::join_lines_all(lines);
    ctx->current_header = effective_header;
    const bool has_prev = !prev_lines.empty();
    const bool visible_changed = prev_lines != lines;
    const std::string animation_mode =
        !animation_mode_hint.empty() ? animation_mode_hint : ctx->config.animation_mode;
    const pipeline::TransitionDecision decision = pipeline::adapt_transition_decision_for_lines(
        prev_lines,
        lines,
        has_prev,
        visible_changed,
        ctx->animating,
        animation_mode,
        transition_hint);
    const bool animate = decision.animate;
    const bool fade_only = decision.fade_only;
    const bool is_strict_roll = decision.strict_roll;
    if (animate && ctx->text_prev && ctx->text_enter) {
      ctx->anim_shift_prev = is_strict_roll;
      ctx->anim_fade_only = fade_only;
      const int lines_for_step = std::max(1, static_cast<int>(lines.size()));
      ctx->line_height = std::max(
          8.0f, static_cast<float>(content_height_px(ctx)) / static_cast<float>(lines_for_step));
      ctx->anim_offset = 0.0f;
      ctx->anim_start_ns = os_gettime_ns();
      ctx->anim_duration_s = fade_only ? 0.12 : 0.18;
      ctx->animating = true;
      update_text_source_lines(ctx, ctx->text_prev, prev_lines, prev_header);
      const std::string enter_line = !enter_line_hint.empty() ? enter_line_hint : lines.back();
      if (!fade_only) {
        update_text_source_lines(ctx, ctx->text_enter, std::vector<std::string>{enter_line}, "");
      }
      update_header_source(ctx, effective_header);
      update_text_source_lines(ctx, ctx->text_source, lines, effective_header);
      if (fade_only) {
        set_text_source_alpha(ctx, ctx->text_prev, 1.0f);
        set_text_source_alpha(ctx, ctx->text_source, 0.0f);
      } else {
        set_text_source_alpha(ctx, ctx->text_prev, 1.0f);
        set_text_source_alpha(ctx, ctx->text_source, 1.0f);
      }
    } else {
      ctx->animating = false;
      ctx->anim_offset = 0.0f;
      ctx->anim_fade_only = false;
      update_header_source(ctx, effective_header);
      update_text_source_lines(ctx, ctx->text_source, lines, effective_header);
      set_text_source_alpha(ctx, ctx->text_source, 1.0f);
    }
    ctx->wrapped_text = layout::join_lines_all(lines);
    return;
  }
  const std::string prev_text = ctx->current_text;
  const std::string prev_header = ctx->current_header;
  const std::string animation_mode = !animation_mode_hint.empty() ? animation_mode_hint : ctx->config.animation_mode;
  (void)prev_header;
  ctx->current_lines.clear();
  if (!segment_ids.empty() && segment_ids.size() == segments.size()) {
    ctx->current_segment_ids = segment_ids;
    ctx->current_segments = segments;
    ctx->current_spans = spans;
  } else {
    ctx->current_segment_ids.clear();
    ctx->current_segments.clear();
    ctx->current_spans.clear();
  }
  ctx->current_text = text;
  ctx->current_header = effective_header;
#ifdef what_overlay_debug
  blog(LOG_INFO, "what_overlay: apply_pending text_len=%zu header_len=%zu",
       text.size(), header.size());
#endif
  const bool has_prev = !prev_text.empty();
  const std::string next_combined = text;
  const BoxTextResult next_fit =
      fit_text_to_box_dispatch(ctx, next_combined, content_width_px(ctx), content_height_px(ctx), ctx->config.font_size_px,
                               ctx->config.max_segments, ctx->config.auto_shrink_to_fit, ctx->config.no_word_split);
  const std::string prev_combined = prev_text;
  const BoxTextResult prev_fit =
      fit_text_to_box_dispatch(ctx, prev_combined, content_width_px(ctx), content_height_px(ctx), ctx->config.font_size_px,
                               ctx->config.max_segments, ctx->config.auto_shrink_to_fit, ctx->config.no_word_split);
  const auto prev_visible_lines = layout::split_lines(prev_fit.visible);
  const auto next_visible_lines = layout::split_lines(next_fit.visible);
  const bool visible_changed = prev_fit.visible != next_fit.visible;
  const pipeline::TransitionDecision decision = pipeline::adapt_transition_decision_for_text(
      prev_visible_lines,
      next_visible_lines,
      has_prev,
      visible_changed,
      ctx->animating,
      animation_mode);
  const bool animate = decision.animate;
  const bool fade_only = decision.fade_only;
  const bool is_strict_roll = decision.strict_roll;
  if (has_prev) {
#ifdef what_overlay_debug
    auto count_lines = [](const std::string& value) {
      if (value.empty()) return 0;
      int count = 1;
      for (char c : value) {
        if (c == '\n') count++;
      }
      return count;
    };
    const int prev_lines = count_lines(prev_fit.full_wrapped);
    const int next_lines = count_lines(next_fit.full_wrapped);
    blog(LOG_INFO,
         "what_overlay: animate_check prev_len=%zu next_len=%zu prev_lines=%d next_lines=%d animate=%s",
         prev_fit.full_wrapped.size(), next_fit.full_wrapped.size(), prev_lines, next_lines,
         animate ? "yes" : "no");
#endif
  }
  if (animate && ctx->text_prev) {
    // Set animation state first so render never shows a transient full-new frame.
    ctx->anim_shift_prev = is_strict_roll;
    ctx->anim_fade_only = fade_only;
    const int lines_for_step = std::max(1, static_cast<int>(next_visible_lines.size()));
    ctx->line_height = std::max(
        8.0f, static_cast<float>(content_height_px(ctx)) / static_cast<float>(lines_for_step));
    ctx->anim_offset = 0.0f;
    ctx->anim_start_ns = os_gettime_ns();
    ctx->anim_duration_s = fade_only ? 0.12 : 0.18;
    ctx->animating = true;

    update_text_source(ctx, ctx->text_prev, prev_text, prev_header);
    if (!fade_only && ctx->text_enter && !next_visible_lines.empty()) {
      update_text_source(ctx, ctx->text_enter, next_visible_lines.back(), "");
    }
    update_header_source(ctx, effective_header);
    update_text_source(ctx, ctx->text_source, text, effective_header);
    if (fade_only) {
      set_text_source_alpha(ctx, ctx->text_prev, 1.0f);
      set_text_source_alpha(ctx, ctx->text_source, 0.0f);
    } else {
      set_text_source_alpha(ctx, ctx->text_prev, 1.0f);
      set_text_source_alpha(ctx, ctx->text_source, 1.0f);
    }
    ctx->wrapped_text = next_fit.full_wrapped;
  } else {
    ctx->animating = false;
    ctx->anim_offset = 0.0f;
    ctx->anim_fade_only = false;
    update_header_source(ctx, effective_header);
    update_text_source(ctx, ctx->text_source, text, effective_header);
    set_text_source_alpha(ctx, ctx->text_source, 1.0f);
    ctx->wrapped_text = next_fit.full_wrapped;
  }
}

}  // namespace what_overlay
