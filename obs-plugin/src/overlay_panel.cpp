#include "what_overlay/overlay_panel.h"
#include "what_overlay/overlay_state.h"
#include "what_overlay/panel/box_logic.h"

#include <obs-module.h>
#include <obs-frontend-api.h>

#include <algorithm>
#include <cmath>
#include <map>
#include <string>
#include <unordered_set>
#include <vector>

#if defined(WHAT_OVERLAY_HAS_QT_DOCK)
#include <QAction>
#include <QDialog>
#include <QColorDialog>
#include <QComboBox>
#include <QCheckBox>
#include <QDoubleSpinBox>
#include <QFont>
#include <QFontMetrics>
#include <QFontComboBox>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QButtonGroup>
#include <QHash>
#include <QPainter>
#include <QPointer>
#include <QSizePolicy>
#include <QSlider>
#include <QSpinBox>
#include <QScrollBar>
#include <QString>
#include <QStringList>
#include <QToolButton>
#include <QToolTip>
#include <QTimer>
#include <QIntValidator>
#include <QEvent>
#include <QKeySequence>
#include <QScrollArea>
#include <QSettings>
#include <QTextEdit>
#include <QVBoxLayout>
#include <QWidget>
#include <QEventLoop>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrl>
#include <QDateTime>
// Pulled in transitively by newer Qt headers, but not by Qt 6.4.
#include <QCoreApplication>
#include <QtGlobal>
#include <utility>

// QCheckBox::checkStateChanged(Qt::CheckState) only exists from Qt 6.7; before that the
// signal is stateChanged(int), carrying the same Qt::CheckState values. OBS ships a
// different Qt per platform -- 6.4.2 from the distro on Linux Mint here, newer inside the
// macOS app bundle -- so route every checkbox connect through one shim rather than
// version-guarding eight call sites.
template <typename F>
static inline void what_connect_check_state(QCheckBox* box, F&& fn)
{
#if QT_VERSION >= QT_VERSION_CHECK(6, 7, 0)
  QObject::connect(box, &QCheckBox::checkStateChanged, std::forward<F>(fn));
#else
  QObject::connect(box, &QCheckBox::stateChanged, [fn = std::forward<F>(fn)](int state) {
    fn(static_cast<Qt::CheckState>(state));
  });
#endif
}
#endif

namespace what_overlay {
namespace {

constexpr const char* kMenuLabel = "What Captions Panel";
constexpr const char* kDockTitle = "What Captions";
constexpr int kLabelWidth = 76;
constexpr int kFieldMinWidth = 118;
bool g_registered = false;
bool g_syncing_geometry = false;
bool g_admin_warmup_done = false;

#if defined(WHAT_OVERLAY_HAS_QT_DOCK)
QAction* g_tools_action = nullptr;
QDialog* g_window = nullptr;
std::vector<std::string> g_active_sources = {"mic", "desktop"};
QCheckBox* g_source_mic_enabled = nullptr;
QCheckBox* g_source_desktop_enabled = nullptr;
QCheckBox* g_source_desktop_installed = nullptr;
QComboBox* g_per_app_audio_combo = nullptr;
QCheckBox* g_box_mic_visible = nullptr;
QCheckBox* g_box_desktop_visible = nullptr;
QCheckBox* g_box_mic_label = nullptr;
QCheckBox* g_box_desktop_label = nullptr;
QCheckBox* g_all_box_labels = nullptr;
QComboBox* g_style_target = nullptr;
QLabel* g_style_target_label = nullptr;
QLabel* g_controller_status = nullptr;
QLabel* g_geometry_status = nullptr;
QSpinBox* g_delay = nullptr;
QSpinBox* g_max_segments = nullptr;
QSpinBox* g_max_chars = nullptr;
QDoubleSpinBox* g_font_size = nullptr;
QLabel* g_effective_font_size = nullptr;
QPushButton* g_use_rendered_as_base = nullptr;
QCheckBox* g_auto_fit_text = nullptr;
QSpinBox* g_width = nullptr;
QSpinBox* g_height = nullptr;
QSpinBox* g_pad_x = nullptr;
QSpinBox* g_pad_y = nullptr;
QCheckBox* g_outline_enabled = nullptr;
QSpinBox* g_outline_thickness = nullptr;
QFontComboBox* g_font_family = nullptr;
QButtonGroup* g_align_group = nullptr;
QToolButton* g_align_left = nullptr;
QToolButton* g_align_center = nullptr;
QToolButton* g_align_right = nullptr;
QToolButton* g_align_justify = nullptr;
QComboBox* g_animation_mode = nullptr;
QPushButton* g_test_stream = nullptr;
QPushButton* g_text_color = nullptr;
QPushButton* g_bg_color = nullptr;
QSlider* g_text_opacity_slider = nullptr;
QSlider* g_bg_opacity_slider = nullptr;
QLineEdit* g_text_opacity_value = nullptr;
QLineEdit* g_bg_opacity_value = nullptr;
QSlider* g_font_size_slider = nullptr;
QLabel* g_preview = nullptr;
QLabel* g_live_output_count = nullptr;
QTextEdit* g_live_output = nullptr;
QScrollArea* g_live_output_scroll = nullptr;
QTimer* g_live_output_timer = nullptr;
QTimer* g_runtime_apply_timer = nullptr;
QCheckBox* g_live_colorize = nullptr;
QWidget* g_live_minimap = nullptr;
QString g_live_output_last_html;
QString g_text_color_value = "#FFFFFFFF";
QString g_bg_color_value = "#00000000";
int g_color_hover_gen = 0;
QHash<QString, QString> g_segment_color_by_id;
int g_segment_color_next = 0;
struct ControllerPostResult {
  bool ok = false;
  int status_code = 0;
  QString body;
};
static QString color_hover_text(const QString& value);
static QString segment_color_css(const QString& segment, int idx);
static QString make_live_output_html(const OverlayStateSnapshot& snapshot);
static void normalize_selected_what_scene_item();
static ControllerPostResult post_controller_json(const QString& base_url, const QString& path, const QJsonObject& payload);
static void maybe_warmup_admin_auth(const QString& base_url);
static QJsonObject get_controller_status(const QString& base_url);
static void blog_controller_stream_log_tail(const QString& base_url, int max_lines = 16);
static QString pick_desktop_device_selector(const QString& base_url);
static void publish_overlay_geometry_to_controller_if_changed(int width_px, int height_px, int padding_px, double font_size_px);
static void refresh_controller_controls();
static bool toggle_controller_stream_for_mode(const QString& mode);
static void schedule_runtime_apply();
static void persist_config_to_selected_source(const OverlayConfig& cfg);
struct NormalizeCtx;
struct BoxSceneItemFindCtx {
  std::string box;
  obs_sceneitem_t* match = nullptr;
};
static bool find_what_scene_item(obs_scene_t* scene, obs_sceneitem_t* item, void* data);
static bool find_what_scene_item_for_box(obs_scene_t* scene, obs_sceneitem_t* item, void* data);
static bool resolve_target_what_scene_item(
    obs_source_t** out_scene_source, obs_sceneitem_t** out_item, obs_source_t** out_source);
static void sync_geometry_from_scene_item();
static void apply_geometry_from_ui();
static void persist_panel_window_geometry(QDialog* window);
static void restore_panel_window_geometry(QDialog* window);
static bool set_box_visibility_in_current_scene(const std::string& box, bool visible, bool with_labels);
static bool is_box_visible_in_current_scene(const std::string& box);
static std::string selected_box_in_current_scene();
static void apply_header_for_source(const std::string& box, bool with_label);
static void apply_headers_for_box_labels(bool with_labels);
static void refresh_box_toggle_labels();
static void update_all_labels_state();
static void rebuild_style_target_items();
static std::string style_target_value();
static void sync_style_target_from_selected_source();

class LiveMiniMap : public QWidget {
 public:
  explicit LiveMiniMap(QWidget* parent = nullptr) : QWidget(parent) { setFixedSize(46, 46); }

  void set_view(int total_w, int total_h, int x, int y, int view_w, int view_h) {
    total_w_ = std::max(1, total_w);
    total_h_ = std::max(1, total_h);
    x_ = std::max(0, x);
    y_ = std::max(0, y);
    view_w_ = std::max(1, view_w);
    view_h_ = std::max(1, view_h);
    update();
  }

 protected:
  void paintEvent(QPaintEvent* /*event*/) override {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    const QRectF outer = rect().adjusted(2, 2, -2, -2);
    p.setPen(QPen(QColor("#b30000"), 2));
    p.setBrush(QColor(80, 0, 0, 40));
    p.drawRect(outer);

    const double sx = outer.width() / static_cast<double>(total_w_);
    const double sy = outer.height() / static_cast<double>(total_h_);
    QRectF inner(
        outer.left() + (static_cast<double>(x_) * sx),
        outer.top() + (static_cast<double>(y_) * sy),
        std::max(2.0, static_cast<double>(view_w_) * sx),
        std::max(2.0, static_cast<double>(view_h_) * sy));
    inner = inner.intersected(outer);
    p.setPen(QPen(QColor("#ffffff"), 1.5));
    p.setBrush(Qt::NoBrush);
    p.drawRect(inner);
  }

 private:
  int total_w_ = 1;
  int total_h_ = 1;
  int x_ = 0;
  int y_ = 0;
  int view_w_ = 1;
  int view_h_ = 1;
};

static void update_live_minimap() {
  // Minimap is currently disabled (see KNOWN_ISSUES.md).
}

class DelayedColorTooltipFilter : public QObject {
 public:
  explicit DelayedColorTooltipFilter(const QString* value_ref, QObject* parent = nullptr)
      : QObject(parent), value_ref_(value_ref) {}

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override {
    auto* button = qobject_cast<QPushButton*>(watched);
    if (!button || !value_ref_) return QObject::eventFilter(watched, event);
    if (event->type() == QEvent::Enter) {
      const int gen = ++g_color_hover_gen;
      QTimer::singleShot(1500, button, [button, this, gen]() {
        if (gen != g_color_hover_gen || !button->underMouse()) return;
        const QPoint pos = button->mapToGlobal(QPoint(button->width() / 2, button->height() + 4));
        QToolTip::showText(pos, color_hover_text(*value_ref_), button);
      });
    } else if (event->type() == QEvent::Leave || event->type() == QEvent::MouseButtonPress) {
      ++g_color_hover_gen;
      QToolTip::hideText();
    }
    return QObject::eventFilter(watched, event);
  }

 private:
  const QString* value_ref_;
};

class PanelWindowStateFilter : public QObject {
 public:
  explicit PanelWindowStateFilter(QDialog* window, QObject* parent = nullptr)
      : QObject(parent), window_(window) {}

 protected:
  bool eventFilter(QObject* watched, QEvent* event) override {
    if (!window_ || watched != window_) return QObject::eventFilter(watched, event);
    if (event->type() == QEvent::Move || event->type() == QEvent::Resize || event->type() == QEvent::Hide ||
        event->type() == QEvent::Close) {
      persist_panel_window_geometry(window_);
    }
    return QObject::eventFilter(watched, event);
  }

 private:
  QPointer<QDialog> window_;
};

static QSettings panel_window_settings() {
  char* path = obs_module_config_path("panel_window.ini");
  if (path) {
    const QString ini_path = QString::fromUtf8(path);
    bfree(path);
    if (!ini_path.isEmpty()) return QSettings(ini_path, QSettings::IniFormat);
  }
  // Fallback for unexpected module-config path failures.
  return QSettings(QStringLiteral("what_overlay"), QStringLiteral("obs_panel_window"));
}

static void persist_panel_window_geometry(QDialog* window) {
  if (!window) return;
  QSettings settings = panel_window_settings();
  const QRect r = window->geometry();
  settings.setValue(QStringLiteral("x"), r.x());
  settings.setValue(QStringLiteral("y"), r.y());
  settings.setValue(QStringLiteral("w"), r.width());
  settings.setValue(QStringLiteral("h"), r.height());
  settings.sync();
}

static void restore_panel_window_geometry(QDialog* window) {
  if (!window) return;
  QSettings settings = panel_window_settings();
  const bool has_all = settings.contains(QStringLiteral("x")) && settings.contains(QStringLiteral("y")) &&
                       settings.contains(QStringLiteral("w")) && settings.contains(QStringLiteral("h"));
  if (!has_all) return;
  const int x = settings.value(QStringLiteral("x")).toInt();
  const int y = settings.value(QStringLiteral("y")).toInt();
  const int w = std::max(window->minimumWidth(), settings.value(QStringLiteral("w")).toInt());
  const int h = std::max(window->minimumHeight(), settings.value(QStringLiteral("h")).toInt());
  if (w > 0 && h > 0) window->setGeometry(x, y, w, h);
}

static Qt::Alignment preview_alignment_from_string(const std::string& value) {
  if (value == "center") return Qt::AlignHCenter | Qt::AlignVCenter;
  if (value == "right") return Qt::AlignRight | Qt::AlignVCenter;
  if (value == "justify") return Qt::AlignJustify | Qt::AlignVCenter;
  return Qt::AlignLeft | Qt::AlignVCenter;
}

static std::string align_string_from_buttons() {
  if (g_align_center && g_align_center->isChecked()) return "center";
  if (g_align_right && g_align_right->isChecked()) return "right";
  if (g_align_justify && g_align_justify->isChecked()) return "justify";
  return "left";
}

static void select_align_button(const std::string& align) {
  if (!g_align_left || !g_align_center || !g_align_right || !g_align_justify) return;
  if (align == "center") {
    g_align_center->setChecked(true);
  } else if (align == "right") {
    g_align_right->setChecked(true);
  } else if (align == "justify") {
    g_align_justify->setChecked(true);
  } else {
    g_align_left->setChecked(true);
  }
}

static QColor color_from_aarrggbb(const QString& value, const QColor& fallback) {
  QString v = value.trimmed();
  if (v.startsWith("#")) v = v.mid(1);
  if (v.size() != 8) return fallback;
  bool ok = false;
  const uint32_t raw = v.toUInt(&ok, 16);
  if (!ok) return fallback;
  const int a = static_cast<int>((raw >> 24) & 0xFF);
  const int r = static_cast<int>((raw >> 16) & 0xFF);
  const int g = static_cast<int>((raw >> 8) & 0xFF);
  const int b = static_cast<int>(raw & 0xFF);
  return QColor(r, g, b, a);
}

static QString color_to_aarrggbb(const QColor& c) {
  return QString("#%1%2%3%4")
      .arg(c.alpha(), 2, 16, QLatin1Char('0'))
      .arg(c.red(), 2, 16, QLatin1Char('0'))
      .arg(c.green(), 2, 16, QLatin1Char('0'))
      .arg(c.blue(), 2, 16, QLatin1Char('0'))
      .toUpper();
}

static int opacity_percent_from_aarrggbb(const QString& value, int fallback) {
  QString v = value.trimmed();
  if (v.startsWith("#")) v = v.mid(1);
  if (v.size() != 8) return fallback;
  bool ok = false;
  const uint32_t raw = v.toUInt(&ok, 16);
  if (!ok) return fallback;
  const int a = static_cast<int>((raw >> 24) & 0xFF);
  return static_cast<int>(std::lround((static_cast<double>(a) / 255.0) * 100.0));
}

static QString set_aarrggbb_opacity(const QString& value, int opacity_percent) {
  QColor c = color_from_aarrggbb(value, QColor(255, 255, 255, 255));
  const int pct = std::max(0, std::min(100, opacity_percent));
  c.setAlpha(static_cast<int>(std::lround((static_cast<double>(pct) / 100.0) * 255.0)));
  return color_to_aarrggbb(c);
}

static QString color_hover_text(const QString& value) {
  const QColor c = color_from_aarrggbb(value, QColor(255, 255, 255, 255));
  return QString("HEX: %1\nRGBA: (%2, %3, %4, %5)\nOpacity: %6%")
      .arg(value.toUpper())
      .arg(c.red())
      .arg(c.green())
      .arg(c.blue())
      .arg(c.alpha())
      .arg(opacity_percent_from_aarrggbb(value, 100));
}

static void set_color_button(QPushButton* button, const QString& value) {
  if (!button) return;
  const QColor c = color_from_aarrggbb(value, QColor(255, 255, 255, 255));
  button->setText("");
  button->setToolTip(color_hover_text(value));
  button->setFixedWidth(30);
  button->setFixedHeight(16);
  button->setMinimumWidth(30);
  button->setMaximumWidth(30);
  button->setMinimumHeight(16);
  button->setMaximumHeight(16);
  button->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
  button->setStyleSheet(
      QString("QPushButton{background-color: rgba(%1,%2,%3,%4); border:1px solid #6a6a6a; border-radius:2px;}")
          .arg(c.red())
          .arg(c.green())
          .arg(c.blue())
          .arg(c.alpha()));
}

static void setup_delayed_color_tooltip(QPushButton* button, const QString* value_ref) {
  if (!button || !value_ref) return;
  button->installEventFilter(new DelayedColorTooltipFilter(value_ref, button));
}

static void add_grid_row(QGridLayout* grid, int row, QWidget* parent, const QString& left_label,
                         QWidget* left_widget, const QString& right_label, QWidget* right_widget) {
  auto* left = new QLabel(left_label, parent);
  left->setFixedWidth(kLabelWidth);
  auto* right = new QLabel(right_label, parent);
  right->setFixedWidth(kLabelWidth);
  left_widget->setMinimumWidth(kFieldMinWidth);
  right_widget->setMinimumWidth(kFieldMinWidth);
  left_widget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  right_widget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  grid->addWidget(left, row, 0);
  grid->addWidget(left_widget, row, 1);
  grid->addWidget(right, row, 2);
  grid->addWidget(right_widget, row, 3);
}

static void update_preview() {
  if (!g_preview) return;
  QFont preview_font = g_preview->font();
  if (g_font_family) preview_font.setFamily(g_font_family->currentFont().family());
  if (g_font_size) preview_font.setPointSizeF(std::max(1.0, g_font_size->value()));
  g_preview->setFont(preview_font);
  g_preview->setAlignment(preview_alignment_from_string(align_string_from_buttons()));

  const QColor fg = color_from_aarrggbb(g_text_color_value, QColor(255, 255, 255, 255));
  const QColor bg = color_from_aarrggbb(g_bg_color_value, QColor(0, 0, 0, 0));
  g_preview->setStyleSheet(
      QString("QLabel{border:1px solid #3f3f3f; border-radius:4px; padding:6px; "
              "color: rgba(%1,%2,%3,%4); background-color: rgba(%5,%6,%7,%8);}")
          .arg(fg.red())
          .arg(fg.green())
          .arg(fg.blue())
          .arg(fg.alpha())
          .arg(bg.red())
          .arg(bg.green())
          .arg(bg.blue())
          .arg(bg.alpha()));
}

static QString segment_color_css(const QString& segment, int idx) {
  Q_UNUSED(idx);
  static const QStringList kPalette = {
      "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#ffff33",
      "#a65628", "#f781bf", "#1b9e77", "#d95f02", "#7570b3", "#e7298a",
      "#66a61e", "#e6ab02", "#a6761d", "#666666", "#17becf", "#bcbd22",
      "#8c564b", "#9467bd", "#2ca02c", "#d62728", "#1f77b4", "#ff9896",
      "#98df8a", "#c5b0d5", "#ffbb78", "#c49c94", "#f7b6d2", "#9edae5"
  };
  const QString key = segment.isEmpty() ? QStringLiteral("__empty__") : segment;
  auto it = g_segment_color_by_id.find(key);
  if (it != g_segment_color_by_id.end()) return it.value();
  const QString color = kPalette[g_segment_color_next % kPalette.size()];
  g_segment_color_next += 1;
  g_segment_color_by_id.insert(key, color);
  return color;
}

static QString make_live_output_html(const OverlayStateSnapshot& snapshot) {
  constexpr double kObsFontScale = 6.0;
  const QString align =
      snapshot.config.align == "center" ? "center" :
      snapshot.config.align == "right" ? "right" :
      snapshot.config.align == "justify" ? "justify" : "left";
  const double font_px = std::max(1.0, snapshot.config.font_size_px * kObsFontScale);
  const QString rendered = QString::fromStdString(snapshot.rendered_text);
  const int content_w = std::max(24, snapshot.config.width_px - (snapshot.config.padding_x_px * 2));
  const int content_h = std::max(24, snapshot.config.height_px - (snapshot.config.padding_y_px * 2));
  QString html;
  html += "<div style='white-space: pre-wrap; overflow:hidden; width:";
  html += QString::number(content_w);
  html += "px; min-height:";
  html += QString::number(content_h);
  html += "px; font-family:\"";
  html += QString::fromStdString(snapshot.config.font_family).toHtmlEscaped();
  html += "\"; font-size:";
  html += QString::number(font_px, 'f', 2);
  html += "px; text-align:";
  html += align;
  html += ";'>";
  const bool colorize = g_live_colorize && g_live_colorize->isChecked();
  if (!colorize) {
    html += rendered.toHtmlEscaped();
  } else if (!snapshot.rendered_spans.empty()) {
    size_t cursor = 0;
    for (const auto& span : snapshot.rendered_spans) {
      if (span.end <= span.start || span.start >= snapshot.rendered_text.size()) continue;
      const size_t safe_start = std::min(span.start, snapshot.rendered_text.size());
      const size_t safe_end = std::min(span.end, snapshot.rendered_text.size());
      if (safe_start > cursor) {
        html += QString::fromStdString(
            snapshot.rendered_text.substr(cursor, safe_start - cursor)).toHtmlEscaped();
      }
      const QString color = segment_color_css(QString::fromStdString(span.segment_id), 0);
      html += "<span style='color:";
      html += color;
      html += ";'>";
      html += QString::fromStdString(
          snapshot.rendered_text.substr(safe_start, safe_end - safe_start)).toHtmlEscaped();
      html += "</span>";
      cursor = safe_end;
    }
    if (cursor < snapshot.rendered_text.size()) {
      html += QString::fromStdString(snapshot.rendered_text.substr(cursor)).toHtmlEscaped();
    }
  } else {
    html += rendered.toHtmlEscaped();
  }
  html += "</div>";
  return html;
}

static int unique_visible_segment_count(const OverlayStateSnapshot& snapshot) {
  std::unordered_set<std::string> unique_ids;
  if (!snapshot.rendered_spans.empty()) {
    for (const auto& span : snapshot.rendered_spans) {
      if (!span.segment_id.empty()) unique_ids.insert(span.segment_id);
    }
  }
  if (!snapshot.rendered_segment_ids.empty()) {
    for (const auto& id : snapshot.rendered_segment_ids) {
      if (!id.empty()) unique_ids.insert(id);
    }
  }
  if (unique_ids.empty() && !snapshot.rendered_segments.empty()) {
    for (size_t i = 0; i < snapshot.rendered_segments.size(); ++i) {
      unique_ids.insert("seg-" + std::to_string(i));
    }
  }
  return static_cast<int>(unique_ids.size());
}

static void sync_live_output_bounds(const OverlayConfig& cfg) {
  if (!g_live_output) return;
  const int content_w = std::max(24, cfg.width_px - (cfg.padding_x_px * 2));
  const int content_h = std::max(24, cfg.height_px - (cfg.padding_y_px * 2));
  const int max_preview_w = 300;
  const int max_preview_h = 108;
  double scale = std::min(
      1.0,
      std::min(
          static_cast<double>(max_preview_w) / static_cast<double>(content_w),
          static_cast<double>(max_preview_h) / static_cast<double>(content_h)));
  if (scale <= 0.0) scale = 1.0;
  const int preview_w = std::max(24, static_cast<int>(std::lround(content_w * scale)));
  const int preview_h = std::max(24, static_cast<int>(std::lround(content_h * scale)));
  g_live_output->setFixedSize(preview_w, preview_h);
  g_live_output->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
  if (g_live_output_scroll) {
    g_live_output_scroll->setFixedSize(preview_w, preview_h);
    g_live_output_scroll->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
  }
}

static int font_slider_from_value(double value) {
  return static_cast<int>(std::lround(std::max(0.1, std::min(40.0, value)) * 20.0));
}

static double font_value_from_slider(int slider_value) {
  return std::max(0.1, std::min(40.0, static_cast<double>(slider_value) / 20.0));
}

static void load_snapshot_to_ui() {
  g_syncing_geometry = true;
  const OverlayStateSnapshot snapshot = overlay_state_snapshot();
  OverlayConfig cfg = snapshot.config;
  bool any_test_stream_enabled = false;
  bool saw_test_stream_source = false;
  const std::string target_mode = style_target_value();
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (current_scene_src) {
    obs_scene_t* scene = obs_scene_from_source(current_scene_src);
    if (scene) {
      for (const std::string& box : g_active_sources) {
        BoxSceneItemFindCtx stream_ctx{box, nullptr};
        obs_scene_enum_items(scene, find_what_scene_item_for_box, &stream_ctx);
        if (!stream_ctx.match) continue;
        obs_source_t* stream_src = obs_sceneitem_get_source(stream_ctx.match);
        if (!stream_src) continue;
        obs_data_t* stream_settings = obs_source_get_settings(stream_src);
        if (stream_settings) {
          saw_test_stream_source = true;
          any_test_stream_enabled =
              any_test_stream_enabled || obs_data_get_bool(stream_settings, "test_stream");
          obs_data_release(stream_settings);
        }
      }
      if (target_mode == "mic" || target_mode == "desktop") {
        BoxSceneItemFindCtx ctx{target_mode, nullptr};
        obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
        if (ctx.match) {
          obs_source_t* src = obs_sceneitem_get_source(ctx.match);
          if (src) {
            obs_data_t* settings = obs_source_get_settings(src);
            cfg.max_segments = static_cast<int>(obs_data_get_int(settings, "max_segments"));
            cfg.max_chars = static_cast<int>(obs_data_get_int(settings, "max_chars"));
            cfg.font_size_px = obs_data_get_double(settings, "font_size");
            cfg.delay_seconds = static_cast<int>(obs_data_get_int(settings, "delay_seconds"));
            cfg.width_px = static_cast<int>(obs_data_get_int(settings, "width"));
            cfg.height_px = static_cast<int>(obs_data_get_int(settings, "height"));
            cfg.padding_x_px = static_cast<int>(obs_data_get_int(settings, "pad_x"));
            cfg.padding_y_px = static_cast<int>(obs_data_get_int(settings, "pad_y"));
            cfg.outline_enabled = obs_data_get_bool(settings, "outline_enabled");
            cfg.outline_thickness_px = static_cast<int>(obs_data_get_int(settings, "outline_thickness_px"));
            const char* align = obs_data_get_string(settings, "align");
            if (align && *align) cfg.align = align;
            const char* anim = obs_data_get_string(settings, "animation_mode");
            if (anim && *anim) cfg.animation_mode = anim;
            const char* text_color = obs_data_get_string(settings, "text_color");
            if (text_color && *text_color) cfg.text_color = text_color;
            const char* bg_color = obs_data_get_string(settings, "bg_color");
            if (bg_color && *bg_color) cfg.bg_color = bg_color;
            obs_data_t* font_obj = obs_data_get_obj(settings, "font");
            if (font_obj) {
              const char* face = obs_data_get_string(font_obj, "face");
              if (face && *face) cfg.font_family = face;
              obs_data_release(font_obj);
            }
            obs_data_release(settings);
          }
        }
      }
    }
    obs_source_release(current_scene_src);
  }
  cfg.test_stream = saw_test_stream_source ? any_test_stream_enabled : cfg.test_stream;
  if (g_max_segments) g_max_segments->setValue(cfg.max_segments);
  if (g_max_chars) g_max_chars->setValue(cfg.max_chars);
  if (g_font_size) g_font_size->setValue(cfg.font_size_px);
  if (g_font_size_slider) g_font_size_slider->setValue(font_slider_from_value(cfg.font_size_px));
  if (g_effective_font_size) {
    g_effective_font_size->setText(
        QString("Rendered: %1 px").arg(snapshot.effective_font_size_px, 0, 'f', 2));
  }
  if (g_use_rendered_as_base) {
    g_use_rendered_as_base->setEnabled(snapshot.effective_font_size_px > 0.0);
  }
  if (g_auto_fit_text) g_auto_fit_text->setChecked(false);
  if (g_delay) g_delay->setValue(cfg.delay_seconds);
  if (g_width) g_width->setValue(cfg.width_px);
  if (g_height) g_height->setValue(cfg.height_px);
  if (g_pad_x) {
    g_pad_x->setMaximum(std::max(0, (cfg.width_px / 2) - 1));
    g_pad_x->setValue(std::max(0, std::min(cfg.padding_x_px, g_pad_x->maximum())));
  }
  if (g_pad_y) {
    g_pad_y->setMaximum(std::max(0, (cfg.height_px / 2) - 1));
    g_pad_y->setValue(std::max(0, std::min(cfg.padding_y_px, g_pad_y->maximum())));
  }
  if (g_outline_enabled) g_outline_enabled->setChecked(cfg.outline_enabled);
  if (g_outline_thickness) {
    g_outline_thickness->setValue(std::max(1, std::min(24, cfg.outline_thickness_px)));
    g_outline_thickness->setEnabled(!g_outline_enabled || g_outline_enabled->isChecked());
  }
  select_align_button(cfg.align);
  if (g_font_family) g_font_family->setCurrentFont(QFont(QString::fromStdString(cfg.font_family)));
  if (g_animation_mode) g_animation_mode->setCurrentText(QString::fromStdString(cfg.animation_mode));
  if (g_test_stream) {
    g_test_stream->setChecked(cfg.test_stream);
    g_test_stream->setText(cfg.test_stream ? "Test Stream: On" : "Test Stream: Off");
    g_test_stream->setProperty("active", cfg.test_stream);
    g_test_stream->setStyleSheet(cfg.test_stream ? "QPushButton{background:#335a38;}" : "");
    blog(LOG_INFO, "what_overlay: panel_load_test_stream any_enabled=%s",
         cfg.test_stream ? "true" : "false");
  }
  g_text_color_value = QString::fromStdString(cfg.text_color.empty() ? "#FFFFFFFF" : cfg.text_color);
  g_bg_color_value = QString::fromStdString(cfg.bg_color.empty() ? "#00000000" : cfg.bg_color);
  if (g_text_opacity_slider) {
    const int v = opacity_percent_from_aarrggbb(g_text_color_value, 100);
    g_text_opacity_slider->setValue(v);
    if (g_text_opacity_value) g_text_opacity_value->setText(QString::number(v));
  }
  if (g_bg_opacity_slider) {
    const int v = opacity_percent_from_aarrggbb(g_bg_color_value, 0);
    g_bg_opacity_slider->setValue(v);
    if (g_bg_opacity_value) g_bg_opacity_value->setText(QString::number(v));
  }
  set_color_button(g_text_color, g_text_color_value);
  set_color_button(g_bg_color, g_bg_color_value);
  if (g_live_output) {
    sync_live_output_bounds(cfg);
    const QColor fg = color_from_aarrggbb(g_text_color_value, QColor(255, 255, 255, 255));
    const QColor bg = color_from_aarrggbb(g_bg_color_value, QColor(0, 0, 0, 0));
    g_live_output->setStyleSheet(
        QString("QTextEdit{border:1px solid #3f3f3f; border-radius:4px;"
                "background-color: rgba(%1,%2,%3,%4); color: rgba(%5,%6,%7,%8);}")
            .arg(bg.red())
            .arg(bg.green())
            .arg(bg.blue())
            .arg(bg.alpha())
            .arg(fg.red())
            .arg(fg.green())
            .arg(fg.blue())
            .arg(fg.alpha()));
    const QString html = make_live_output_html(snapshot);
    if (g_live_output_last_html != html) {
      g_live_output->setHtml(html);
      g_live_output_last_html = html;
    }
  }
  if (g_live_output_count) {
    const int char_count = static_cast<int>(QString::fromStdString(snapshot.rendered_text).size());
    const int seg_count = unique_visible_segment_count(snapshot);
    g_live_output_count->setText(QString("%1 chars | %2 seg").arg(char_count).arg(seg_count));
  }
  update_preview();
  g_syncing_geometry = false;
}

static OverlayConfig collect_ui_config() {
  OverlayConfig cfg = overlay_state_snapshot().config;
  if (g_max_segments) cfg.max_segments = g_max_segments->value();
  if (g_max_chars) cfg.max_chars = g_max_chars->value();
  if (g_font_size) cfg.font_size_px = g_font_size->value();
  if (g_width) cfg.width_px = std::max(100, g_width->value());
  if (g_height) cfg.height_px = std::max(60, g_height->value());
  if (g_auto_fit_text) cfg.auto_shrink_to_fit = false;
  if (g_delay) cfg.delay_seconds = g_delay->value();
  if (g_pad_x) cfg.padding_x_px = std::max(0, std::min(g_pad_x->value(), std::max(0, (cfg.width_px / 2) - 1)));
  if (g_pad_y) cfg.padding_y_px = std::max(0, std::min(g_pad_y->value(), std::max(0, (cfg.height_px / 2) - 1)));
  if (g_outline_enabled) cfg.outline_enabled = g_outline_enabled->isChecked();
  if (g_outline_thickness) cfg.outline_thickness_px = std::max(1, std::min(24, g_outline_thickness->value()));
  cfg.align = align_string_from_buttons();
  if (g_font_family) cfg.font_family = g_font_family->currentFont().family().toStdString();
  if (g_animation_mode) cfg.animation_mode = g_animation_mode->currentText().toStdString();
  if (g_test_stream) cfg.test_stream = g_test_stream->property("active").toBool();
  cfg.text_color = g_text_color_value.toStdString();
  cfg.bg_color = g_bg_color_value.toStdString();
  return cfg;
}

static QString controller_base_url_from_state() {
  const OverlayStateSnapshot snapshot = overlay_state_snapshot();
  const std::string raw = snapshot.config.control_url.empty()
                              ? std::string("http://127.0.0.1:8780")
                              : snapshot.config.control_url;
  return QString::fromStdString(raw);
}

static ControllerPostResult post_controller_json(const QString& base_url, const QString& path, const QJsonObject& payload) {
  ControllerPostResult out;
  QNetworkAccessManager manager;
  const QUrl url(base_url + path);
  QNetworkRequest req(url);
  req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
  QNetworkReply* reply = manager.post(req, QJsonDocument(payload).toJson(QJsonDocument::Compact));
  QEventLoop loop;
  QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
  loop.exec();
  out.status_code = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
  out.body = QString::fromUtf8(reply->readAll()).trimmed();
  out.ok = reply->error() == QNetworkReply::NoError;
  reply->deleteLater();
  return out;
}

static void post_overlay_lane_update(const QString& lane, const OverlayConfig& cfg) {
  const QString lane_norm = lane.trimmed().toLower();
  if (lane_norm != "mic" && lane_norm != "desktop") return;
  const QString base = controller_base_url_from_state();
  const QString msg = QString(
                          "overlay_lane_update lane=%1 max_segments=%2 max_chars=%3 width_px=%4 height_px=%5 font_ui=%6 padding_px=%7")
                          .arg(lane_norm)
                          .arg(cfg.max_segments)
                          .arg(cfg.max_chars)
                          .arg(cfg.width_px)
                          .arg(cfg.height_px)
                          .arg(cfg.font_size_px, 0, 'f', 2)
                          .arg(cfg.padding_x_px);
  QJsonObject payload;
  payload.insert("message", msg);
  const ControllerPostResult r = post_controller_json(base, "/control/session/log", payload);
  blog(r.ok ? LOG_INFO : LOG_WARNING,
       "what_overlay: panel lane sync %s lane=%s (HTTP %d %s)",
       r.ok ? "ok" : "failed", lane_norm.toUtf8().constData(), r.status_code, r.body.toUtf8().constData());
}

static void post_overlay_lane_update_from_scene(const QString& lane);
static void post_overlay_lane_updates_from_scene();

static void maybe_warmup_admin_auth(const QString& base_url) {
  Q_UNUSED(base_url);
  // Disabled: warmup creates an extra auth prompt before each privileged action.
  // Keep helper for possible future session-token approach, but no-op for now.
  g_admin_warmup_done = true;
}

static QJsonObject get_controller_status(const QString& base_url) {
  QNetworkAccessManager manager;
  const QUrl url(base_url + "/control/status");
  QNetworkRequest req(url);
  QNetworkReply* reply = manager.get(req);
  QEventLoop loop;
  QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
  loop.exec();
  if (reply->error() != QNetworkReply::NoError) {
    reply->deleteLater();
    return QJsonObject();
  }
  const QByteArray body = reply->readAll();
  reply->deleteLater();
  const QJsonDocument doc = QJsonDocument::fromJson(body);
  if (!doc.isObject()) return QJsonObject();
  return doc.object();
}

static void blog_controller_stream_log_tail(const QString& base_url, int max_lines) {
  QNetworkAccessManager manager;
  const QUrl url(base_url + "/control/stream/logs?offset=0");
  QNetworkRequest req(url);
  QNetworkReply* reply = manager.get(req);
  QEventLoop loop;
  QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
  loop.exec();
  if (reply->error() != QNetworkReply::NoError) {
    reply->deleteLater();
    return;
  }
  const QByteArray body = reply->readAll();
  reply->deleteLater();
  const QJsonDocument doc = QJsonDocument::fromJson(body);
  if (!doc.isObject()) return;
  const QJsonArray lines = doc.object().value("lines").toArray();
  const int total = lines.size();
  if (total <= 0) return;
  const int start = std::max(0, total - std::max(1, max_lines));
  for (int i = start; i < total; ++i) {
    const QJsonObject row = lines.at(i).toObject();
    const int seq = row.value("seq").toInt(-1);
    const QString line = row.value("line").toString();
    if (!line.isEmpty()) {
      blog(LOG_INFO, "what_overlay: controller_stream_log seq=%d line=%s", seq, line.toUtf8().constData());
    }
  }
}

static QString pick_desktop_device_selector(const QString& base_url) {
  QNetworkAccessManager manager;
  const QUrl url(base_url + "/control/desktop-audio/devices");
  QNetworkRequest req(url);
  QNetworkReply* reply = manager.get(req);
  QEventLoop loop;
  QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
  loop.exec();
  if (reply->error() != QNetworkReply::NoError) {
    reply->deleteLater();
    return QString();
  }
  const QByteArray body = reply->readAll();
  reply->deleteLater();
  const QJsonDocument doc = QJsonDocument::fromJson(body);
  if (!doc.isObject()) return QString();
  const QJsonArray devices = doc.object().value("devices").toArray();
  if (devices.isEmpty()) return QString();

  QString what_value;
  QString what_label;
  QString legacy_what_value;
  QString legacy_what_label;
  QString loopback_value;
  QString loopback_label;
  for (const QJsonValue& entry : devices) {
    if (!entry.isObject()) continue;
    const QJsonObject row = entry.toObject();
    const QString value = row.value("value").toString().trimmed();
    const QString label_raw = row.value("label").toString().trimmed();
    const QString label = label_raw.toLower();
    if (value.isEmpty()) continue;
    if (what_value.isEmpty() && label.contains("what-desktop")) {
      what_value = value;
      what_label = label_raw;
    }
    if (legacy_what_value.isEmpty() && label.startsWith("what-")) {
      legacy_what_value = value;
      legacy_what_label = label_raw;
    }
    if (loopback_value.isEmpty() &&
        (label.contains("blackhole") || label.contains("loopback") || label.contains("soundflower") ||
         label.contains("vb-cable"))) {
      loopback_value = value;
      loopback_label = label_raw;
    }
  }
  QString picked;
  QString picked_label;
  if (!what_value.isEmpty()) {
    picked = what_value;
    picked_label = what_label;
  } else if (!legacy_what_value.isEmpty()) {
    picked = legacy_what_value;
    picked_label = legacy_what_label;
  } else if (!loopback_value.isEmpty()) {
    picked = loopback_value;
    picked_label = loopback_label;
  }
  blog(LOG_INFO, "what_overlay: panel desktop device probe devices=%d picked='%s' label='%s'",
       static_cast<int>(devices.size()), picked.toUtf8().constData(), picked_label.toUtf8().constData());
  return picked;
}

static QString stream_mode_from_status(const QJsonObject& status) {
  const QStringList keys = {"stream_input_mode", "input_mode", "mode", "source", "active_source"};
  for (const QString& key : keys) {
    const QString value = status.value(key).toString().trimmed().toLower();
    if (value == "mic" || value == "desktop") return value;
  }
  return QString();
}

static bool bool_from_status(const QJsonObject& status, const char* key, bool fallback = false) {
  const QJsonValue v = status.value(QString::fromUtf8(key));
  return v.isBool() ? v.toBool() : fallback;
}

static void publish_overlay_geometry_to_controller_if_changed(
    int width_px, int height_px, int padding_px, double font_size_px) {
  static int last_w = -1;
  static int last_h = -1;
  static int last_p = -1;
  static int last_f_milli = -1;
  static qint64 last_fail_ms = 0;

  const int w = std::max(100, width_px);
  const int h = std::max(60, height_px);
  const int p = std::max(0, padding_px);
  const int f_milli = std::max(1, static_cast<int>(std::lround(font_size_px * 1000.0)));
  if (w == last_w && h == last_h && p == last_p && f_milli == last_f_milli) return;

  const qint64 now_ms = QDateTime::currentMSecsSinceEpoch();
  if (last_fail_ms > 0 && (now_ms - last_fail_ms) < 1000) return;

  const QString base = controller_base_url_from_state();
  QJsonObject payload;
  payload.insert("overlay_width_px", w);
  payload.insert("overlay_height_px", h);
  payload.insert("overlay_padding_px", p);
  payload.insert("overlay_font_size_px", static_cast<double>(f_milli) / 1000.0);
  const ControllerPostResult r = post_controller_json(base, "/control/overlay-geometry", payload);
  if (r.ok && r.status_code >= 200 && r.status_code < 300) {
    last_w = w;
    last_h = h;
    last_p = p;
    last_f_milli = f_milli;
    last_fail_ms = 0;
    return;
  }
  last_fail_ms = now_ms;
}

static void refresh_controller_controls() {
  if (!g_controller_status) return;
  const QString base = controller_base_url_from_state();
  const QJsonObject status = get_controller_status(base);
  if (status.isEmpty()) {
    if (g_source_mic_enabled) { QSignalBlocker _b(g_source_mic_enabled); g_source_mic_enabled->setChecked(false); }
    if (g_source_desktop_enabled) { QSignalBlocker _b(g_source_desktop_enabled); g_source_desktop_enabled->setChecked(false); }
    g_controller_status->setText("Transcription: Unreachable");
    g_controller_status->setStyleSheet("color:#c48a8a;");
    return;
  }
  const bool running = status.value("running").toBool(false);
  const bool has_stream_support = status.contains("stream_running");
  const bool stream_running_flag = has_stream_support && status.value("stream_running").toBool(false);
  const QString stream_mode = stream_mode_from_status(status);
  const bool mic_enabled = bool_from_status(status, "stream_mic_enabled", stream_mode == "mic");
  const bool desktop_enabled = bool_from_status(status, "stream_desktop_enabled", stream_mode == "desktop");
  const bool stream_running = stream_running_flag || mic_enabled || desktop_enabled;
  // Update active sources from status; rebuild style-target combobox if list changed.
  {
    std::vector<std::string> new_sources;
    const QJsonArray srcs = status.value("active_sources").toArray();
    if (!srcs.isEmpty()) {
      for (const auto& v : srcs) {
        const std::string s = v.toString().trimmed().toLower().toStdString();
        if (!s.empty()) new_sources.push_back(s);
      }
    }
    if (new_sources.empty()) {
      if (mic_enabled) new_sources.push_back("mic");
      if (desktop_enabled) new_sources.push_back("desktop");
      if (new_sources.empty()) new_sources = {"mic", "desktop"};
    }
    if (new_sources != g_active_sources) {
      g_active_sources = new_sources;
      rebuild_style_target_items();
    }
  }
  const bool mic_active = mic_enabled;
  const bool desktop_active = desktop_enabled;
  if (desktop_active) {
    static qint64 last_desktop_ensure_ms = 0;
    static qint64 desktop_keepalive_pause_until_ms = 0;
    const qint64 now_ms = QDateTime::currentMSecsSinceEpoch();
    if (now_ms < desktop_keepalive_pause_until_ms) {
      // Backoff window after helper timeout/failure.
    } else if ((now_ms - last_desktop_ensure_ms) >= 10000) {
      const ControllerPostResult ensure = post_controller_json(base, "/control/desktop-audio/ensure", QJsonObject{});
      if (!ensure.ok) {
        blog(LOG_WARNING, "what_overlay: panel desktop keepalive ensure failed (HTTP %d %s)", ensure.status_code,
             ensure.body.toUtf8().constData());
        desktop_keepalive_pause_until_ms = now_ms + 15000;
      } else {
        const QJsonDocument parsed = QJsonDocument::fromJson(ensure.body.toUtf8());
        const QJsonObject obj = parsed.isObject() ? parsed.object() : QJsonObject{};
        const bool body_ok = obj.value("ok").toBool(true);
        const QJsonObject ensure_result = obj.value("ensure_result").toObject();
        const QString ensure_error = ensure_result.value("error").toString();
        if (!body_ok || ensure_error == QStringLiteral("coreaudio_helper_timeout")) {
          desktop_keepalive_pause_until_ms = now_ms + 60000;
          blog(LOG_WARNING,
               "what_overlay: panel desktop keepalive entering backoff (error=%s) for 60s",
               ensure_error.toUtf8().constData());
        }
        if (ensure_result.value("changed").toBool(false)) {
          blog(LOG_INFO, "what_overlay: panel desktop keepalive re-routed output (HTTP %d %s)", ensure.status_code,
               ensure.body.toUtf8().constData());
        }
      }
      last_desktop_ensure_ms = now_ms;
    }
  }
  if (g_source_mic_enabled) { QSignalBlocker _b(g_source_mic_enabled); g_source_mic_enabled->setChecked(mic_active); }
  if (g_source_desktop_enabled) { QSignalBlocker _b(g_source_desktop_enabled); g_source_desktop_enabled->setChecked(desktop_active); }
  // Infer installed state from whether the controller knows a desktop device selector.
  if (g_source_desktop_installed && g_source_desktop_installed->isEnabled()) {
    const bool appears_installed = !status.value("stream_desktop_device").toString().trimmed().isEmpty();
    QSignalBlocker _b(g_source_desktop_installed);
    g_source_desktop_installed->setChecked(appears_installed);
    g_source_desktop_installed->setToolTip(appears_installed
        ? "Desktop audio component installed — uncheck to uninstall"
        : "Desktop audio component not installed — check to install");
  }
  QString label;
  if (stream_running) {
    if (stream_mode == "mic") {
      label = QStringLiteral("Transcription: Running (Mic)");
    } else if (stream_mode == "desktop") {
      label = QStringLiteral("Transcription: Running (Desktop)");
    } else {
      label = QStringLiteral("Transcription: Running");
    }
  } else if (running) {
    label = has_stream_support ? QStringLiteral("Transcription: Stopped (Service Running)")
                               : QStringLiteral("Transcription: Stopped (Legacy Controller)");
  } else {
    label = QStringLiteral("Transcription: Stopped");
  }
  g_controller_status->setText(label);
  g_controller_status->setStyleSheet(stream_running ? "color:#8fcf9f;" : "color:#a6adba;");
}

static bool apply_controller_stream_sources(bool enable_mic, bool enable_desktop) {
  const QString base = controller_base_url_from_state();
  const QJsonObject status = get_controller_status(base);
  const bool stream_running = status.value("stream_running").toBool(false);
  const bool has_stream_support = status.contains("stream_running");
  bool ok = false;
  QString fail_reason;

  const auto stop_stream = [&](const char* reason, bool persist_sources, bool preserve_desktop_audio) -> bool {
    QJsonObject payload;
    payload.insert("preserve_desktop_audio", preserve_desktop_audio);
    if (persist_sources) {
      payload.insert("input_mode", enable_mic ? "mic" : "desktop");
      payload.insert("mic_enabled", enable_mic);
      payload.insert("desktop_enabled", enable_desktop);
    }
    const ControllerPostResult r = post_controller_json(base, "/control/stream/stop", payload);
    const bool stop_ok = r.ok;
    blog(stop_ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel stream stop reason=%s %s (HTTP %d %s)", reason,
         stop_ok ? "ok" : "failed", r.status_code, r.body.toUtf8().constData());
    if (!stop_ok) fail_reason = QString("HTTP %1 %2").arg(r.status_code).arg(r.body);
    return stop_ok;
  };

  const auto start_stream = [&]() -> bool {
    QString resolved_mic_backend = status.value("stream_mic_backend").toString().trimmed();
    QString resolved_mic_device = status.value("stream_mic_device").toString().trimmed();
    QString resolved_desktop_backend = status.value("stream_desktop_backend").toString().trimmed();
    QString resolved_desktop_device = status.value("stream_desktop_device").toString().trimmed();
    if (enable_desktop) {
      maybe_warmup_admin_auth(base);
      const ControllerPostResult install = post_controller_json(base, "/control/desktop-audio/install", QJsonObject{});
      blog(install.ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel desktop install %s (HTTP %d %s)",
           install.ok ? "ok" : "failed", install.status_code, install.body.toUtf8().constData());
      const ControllerPostResult ensure = post_controller_json(base, "/control/desktop-audio/ensure", QJsonObject{});
      blog(ensure.ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel desktop ensure %s (HTTP %d %s)",
           ensure.ok ? "ok" : "failed", ensure.status_code, ensure.body.toUtf8().constData());
      resolved_desktop_device = pick_desktop_device_selector(base);
    }
    if (enable_mic && resolved_mic_backend.isEmpty()) resolved_mic_backend = "avfoundation";
    if (enable_mic && resolved_mic_device.isEmpty()) resolved_mic_device = ":0";
    if (enable_desktop && resolved_desktop_backend.isEmpty()) resolved_desktop_backend = "avfoundation";
    if (enable_desktop && resolved_desktop_device.isEmpty()) {
      resolved_desktop_device = pick_desktop_device_selector(base);
    }
    if (enable_desktop && resolved_desktop_device.isEmpty()) {
      fail_reason = QStringLiteral(
          "No desktop capture device detected. Run desktop setup/install so a loopback capture device (for example BlackHole) is available.");
      blog(LOG_WARNING, "what_overlay: panel stream start aborted (no desktop device)");
      return false;
    }
    QJsonObject payload;
    payload.insert("input_mode", enable_mic ? "mic" : "desktop");
    payload.insert("mic_enabled", enable_mic);
    payload.insert("desktop_enabled", enable_desktop);
    if (!resolved_mic_backend.isEmpty()) payload.insert("mic_backend", resolved_mic_backend);
    if (!resolved_mic_device.isEmpty()) payload.insert("mic_device", resolved_mic_device);
    if (!resolved_desktop_backend.isEmpty()) payload.insert("desktop_backend", resolved_desktop_backend);
    if (!resolved_desktop_device.isEmpty()) payload.insert("desktop_device", resolved_desktop_device);
    payload.insert("event_prefix", "EVENT:");
    ControllerPostResult r = post_controller_json(base, "/control/stream/start", payload);
    bool start_ok = r.ok;
    fail_reason = QString("HTTP %1 %2").arg(r.status_code).arg(r.body);
    QJsonObject stream_start_body;
    {
      const QJsonDocument parsed = QJsonDocument::fromJson(r.body.toUtf8());
      if (parsed.isObject()) stream_start_body = parsed.object();
    }
    if (start_ok && enable_desktop && stream_start_body.contains("stream_desktop_enabled") &&
        !stream_start_body.value("stream_desktop_enabled").toBool(false)) {
      start_ok = false;
      const QString reason = stream_start_body.value("stream_desktop_disabled_reason").toString().trimmed();
      fail_reason = reason.isEmpty() ? QStringLiteral("desktop source disabled by controller")
                                     : QString("desktop source disabled by controller (%1)").arg(reason);
    }
    if (start_ok && enable_mic && stream_start_body.contains("stream_mic_enabled") &&
        !stream_start_body.value("stream_mic_enabled").toBool(false)) {
      start_ok = false;
      fail_reason = QStringLiteral("mic source disabled by controller");
    }
    if (!start_ok) {
      QJsonObject fallback;
      fallback.insert("profile", status.value("profile").toString().isEmpty() ? "cpu_friendly"
                                                                               : status.value("profile").toString());
      fallback.insert("start_stream", true);
      fallback.insert("input_mode", enable_mic ? "mic" : "desktop");
      fallback.insert("mic_enabled", enable_mic);
      fallback.insert("desktop_enabled", enable_desktop);
      if (!resolved_mic_backend.isEmpty()) fallback.insert("mic_backend", resolved_mic_backend);
      if (!resolved_mic_device.isEmpty()) fallback.insert("mic_device", resolved_mic_device);
      if (!resolved_desktop_backend.isEmpty()) fallback.insert("desktop_backend", resolved_desktop_backend);
      if (!resolved_desktop_device.isEmpty()) fallback.insert("desktop_device", resolved_desktop_device);
      fallback.insert("event_prefix", "EVENT:");
      const ControllerPostResult r2 = post_controller_json(base, "/control/start", fallback);
      start_ok = r2.ok;
      fail_reason = QString("stream/start=%1:%2 fallback /control/start=%3:%4")
                        .arg(r.status_code)
                        .arg(r.body)
                        .arg(r2.status_code)
                        .arg(r2.body);
    }
    blog(start_ok ? LOG_INFO : LOG_WARNING,
         "what_overlay: panel stream start mic=%s desktop=%s %s (%s)%s", enable_mic ? "true" : "false",
         enable_desktop ? "true" : "false", start_ok ? "ok" : "failed", fail_reason.toUtf8().constData(),
         has_stream_support ? "" : " [legacy status response]");
    if (!start_ok) return false;
    const QJsonObject post = get_controller_status(base);
    const bool post_stream = post.value("stream_running").toBool(false);
    if (!post_stream) {
      fail_reason = QStringLiteral(
          "controller accepted request but stream not running; restart what control/gui to load stream API");
      blog(LOG_WARNING, "what_overlay: panel stream start failed mic=%s desktop=%s (%s)",
           enable_mic ? "true" : "false", enable_desktop ? "true" : "false", fail_reason.toUtf8().constData());
      return false;
    }
    return true;
  };

  if (!enable_mic && !enable_desktop) {
    // Persist both-disabled state so next session keeps per-source toggles off.
    ok = stop_stream("both_disabled", true, false);
  } else if (stream_running) {
    // 1A policy: disabling desktop should immediately remove desktop-audio artifacts.
    // Keep desktop audio only when desktop will remain enabled after reconfigure.
    ok = stop_stream("reconfigure_sources", false, enable_desktop);
    if (ok) ok = start_stream();
  } else {
    ok = start_stream();
  }

  if (!ok && g_controller_status) {
    g_controller_status->setText("Transcription: Start/Stop failed");
    g_controller_status->setStyleSheet("color:#c48a8a;");
    if (!fail_reason.isEmpty()) g_controller_status->setToolTip(fail_reason);
  }
  const QJsonObject post = get_controller_status(base);
  blog(LOG_INFO,
       "what_overlay: panel stream status running=%s mic_enabled=%s desktop_enabled=%s mode=%s mic_backend=%s desktop_backend=%s",
       post.value("stream_running").toBool(false) ? "true" : "false",
       post.value("stream_mic_enabled").toBool(false) ? "true" : "false",
       post.value("stream_desktop_enabled").toBool(false) ? "true" : "false",
       post.value("stream_input_mode").toString().toUtf8().constData(),
       post.value("stream_mic_backend").toString().toUtf8().constData(),
       post.value("stream_desktop_backend").toString().toUtf8().constData());
  blog_controller_stream_log_tail(base, 20);
  refresh_controller_controls();
  return ok;
}

static bool toggle_controller_stream_for_mode(const QString& mode) {
  const QString target_mode = mode.trimmed().toLower();
  if (target_mode != "mic" && target_mode != "desktop") return false;
  const QString base = controller_base_url_from_state();
  const QJsonObject status = get_controller_status(base);
  const bool stream_running_flag = status.value("stream_running").toBool(false);
  const QString stream_mode = stream_mode_from_status(status);
  bool mic_enabled = bool_from_status(status, "stream_mic_enabled", stream_mode == "mic");
  bool desktop_enabled = bool_from_status(status, "stream_desktop_enabled", stream_mode == "desktop");
  Q_UNUSED(stream_running_flag);
  if (target_mode == "mic") {
    mic_enabled = !mic_enabled;
  } else {
    desktop_enabled = !desktop_enabled;
  }
  return apply_controller_stream_sources(mic_enabled, desktop_enabled);
}

static void schedule_runtime_apply() {
  if (!g_runtime_apply_timer) return;
  g_runtime_apply_timer->start();
}

static void ensure_dock() {
  if (g_window) return;
  auto* window = new QDialog(nullptr);
  window->setWindowTitle(kDockTitle);
  window->setWindowFlag(Qt::Window, true);
  window->setWindowFlag(Qt::WindowStaysOnTopHint, false);
  window->setWindowFlag(Qt::Tool, false);
  auto* body = new QWidget(window);
  auto* root = new QVBoxLayout(body);
  root->setContentsMargins(8, 8, 8, 8);
  root->setSpacing(6);
  auto make_section = [&](const QString& title, bool expanded, QVBoxLayout** out_content) {
    auto* section = new QFrame(body);
    section->setFrameShape(QFrame::StyledPanel);
    section->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    auto* section_layout = new QVBoxLayout(section);
    section_layout->setContentsMargins(0, 0, 0, 0);
    section_layout->setSpacing(0);
    auto* toggle = new QToolButton(section);
    toggle->setText(title);
    toggle->setCheckable(true);
    toggle->setChecked(expanded);
    toggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    toggle->setArrowType(expanded ? Qt::DownArrow : Qt::RightArrow);
    toggle->setStyleSheet("QToolButton{font-weight:600; padding:4px 6px; text-align:left;}");
    auto* content = new QWidget(section);
    content->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    auto* content_layout = new QVBoxLayout(content);
    content_layout->setContentsMargins(8, 4, 8, 8);
    content_layout->setSpacing(6);
    content->setVisible(expanded);
    QObject::connect(toggle, &QToolButton::toggled, [toggle, content, section](bool on) {
      toggle->setArrowType(on ? Qt::DownArrow : Qt::RightArrow);
      content->setVisible(on);
      content->updateGeometry();
      if (content->parentWidget()) content->parentWidget()->updateGeometry();
      if (section && section->window()) {
        QWidget* w = section->window();
        const int keep_w = w->width();
        QPointer<QWidget> wp(w);
        QTimer::singleShot(0, w, [wp, keep_w]() {
          if (!wp) return;
          QWidget* ww = wp.data();
          if (!ww) return;
          if (ww->layout()) {
            ww->layout()->invalidate();
            ww->layout()->activate();
          }
          const int target_h = std::max(1, ww->minimumSizeHint().height());
          ww->setMinimumHeight(target_h);
          ww->resize(keep_w, target_h);
        });
      }
    });
    section_layout->addWidget(toggle);
    section_layout->addWidget(content);
    root->addWidget(section);
    if (out_content) *out_content = content_layout;
  };

  QVBoxLayout* session_content = nullptr;
  QVBoxLayout* sources_content = nullptr;
  QVBoxLayout* flow_content = nullptr;
  QVBoxLayout* window_content = nullptr;
  QVBoxLayout* style_content = nullptr;
  QVBoxLayout* animation_content = nullptr;
  make_section("Session", true, &session_content);
  make_section("Sources", true, &sources_content);
  make_section("Flow Rules", false, &flow_content);
  make_section("Caption Window", false, &window_content);
  make_section("Text Style", true, &style_content);
  make_section("Animation", false, &animation_content);
  root->addStretch(1);

  auto* header_row = new QHBoxLayout();
  auto* title_col = new QVBoxLayout();
  title_col->setContentsMargins(0, 0, 0, 0);
  title_col->setSpacing(2);
  title_col->addWidget(new QLabel("What Captions Panel", body));
  g_controller_status = new QLabel("Service: Unknown", body);
  g_controller_status->setStyleSheet("color:#a6adba;");
  title_col->addWidget(g_controller_status);
  g_geometry_status = new QLabel("Geometry: Linked (scene resize updates box)", body);
  g_geometry_status->setStyleSheet("color:#a6adba;");
  title_col->addWidget(g_geometry_status);
  header_row->addLayout(title_col);
  header_row->addStretch(1);
  session_content->addLayout(header_row);

  // Sources section: grid with column headers + per-source rows.
  {
    // Grid columns: 0=source name, 1=Transcript, 2=Box, 3=Label, 4=Installed
    auto* sources_grid = new QGridLayout();
    sources_grid->setHorizontalSpacing(8);
    sources_grid->setVerticalSpacing(4);
    sources_grid->setColumnStretch(0, 1);
    auto make_col_header = [&](const QString& text, int col) {
      auto* lbl = new QLabel(text, body);
      lbl->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);
      lbl->setStyleSheet("color:#a6adba; font-size:10px;");
      sources_grid->addWidget(lbl, 0, col);
    };
    make_col_header("Transcript", 1);
    make_col_header("Box", 2);
    make_col_header("Label", 3);
    make_col_header("Installed", 4);

    // Mic row
    sources_grid->addWidget(new QLabel("Mic", body), 1, 0);
    g_source_mic_enabled = new QCheckBox(body);
    g_source_mic_enabled->setChecked(true);
    g_source_mic_enabled->setToolTip("Enable mic transcription source");
    sources_grid->addWidget(g_source_mic_enabled, 1, 1, Qt::AlignHCenter);
    g_box_mic_visible = new QCheckBox(body);
    g_box_mic_visible->setChecked(false);
    g_box_mic_visible->setToolTip("Show/hide the Mic caption box in the current OBS scene");
    sources_grid->addWidget(g_box_mic_visible, 1, 2, Qt::AlignHCenter);
    g_box_mic_label = new QCheckBox(body);
    g_box_mic_label->setChecked(true);
    g_box_mic_label->setToolTip("Show source name label in Mic caption box");
    sources_grid->addWidget(g_box_mic_label, 1, 3, Qt::AlignHCenter);
    // col 4 intentionally empty for mic (no install component)

    // Desktop row
    sources_grid->addWidget(new QLabel("Desktop", body), 2, 0);
    g_source_desktop_enabled = new QCheckBox(body);
    g_source_desktop_enabled->setChecked(false);
    g_source_desktop_enabled->setToolTip("Enable desktop audio transcription source");
    sources_grid->addWidget(g_source_desktop_enabled, 2, 1, Qt::AlignHCenter);
    g_box_desktop_visible = new QCheckBox(body);
    g_box_desktop_visible->setChecked(false);
    g_box_desktop_visible->setToolTip("Show/hide the Desktop caption box in the current OBS scene");
    sources_grid->addWidget(g_box_desktop_visible, 2, 2, Qt::AlignHCenter);
    g_box_desktop_label = new QCheckBox(body);
    g_box_desktop_label->setChecked(true);
    g_box_desktop_label->setToolTip("Show source name label in Desktop caption box");
    sources_grid->addWidget(g_box_desktop_label, 2, 3, Qt::AlignHCenter);
    g_source_desktop_installed = new QCheckBox(body);
    g_source_desktop_installed->setChecked(false);
    g_source_desktop_installed->setToolTip(
        "Desktop audio component not installed — check to install");
    sources_grid->addWidget(g_source_desktop_installed, 2, 4, Qt::AlignHCenter);

    sources_content->addLayout(sources_grid);

    // All-labels master toggle below grid
    auto* all_labels_row = new QHBoxLayout();
    g_all_box_labels = new QCheckBox("All Labels", body);
    g_all_box_labels->setTristate(true);
    g_all_box_labels->setCheckState(Qt::Checked);
    g_all_box_labels->setToolTip("Enable/disable source name labels in all caption boxes at once");
    all_labels_row->addStretch(1);
    all_labels_row->addWidget(g_all_box_labels);
    sources_content->addLayout(all_labels_row);

    // Per-app audio piping stub — requires system-level routing (e.g. per-process loopback).
    auto* per_app_row = new QHBoxLayout();
    auto* per_app_label = new QLabel("Per-app audio:", body);
    per_app_label->setFixedWidth(kLabelWidth);
    g_per_app_audio_combo = new QComboBox(body);
    g_per_app_audio_combo->setEnabled(false);
    g_per_app_audio_combo->addItem("Not yet available");
    g_per_app_audio_combo->setToolTip(
        "Per-application audio piping (coming soon — requires system-level audio routing support)");
    per_app_row->addWidget(per_app_label);
    per_app_row->addWidget(g_per_app_audio_combo, 1);
    sources_content->addLayout(per_app_row);
  }

  auto* flow_grid = new QGridLayout();
  flow_grid->setHorizontalSpacing(4);
  flow_grid->setVerticalSpacing(6);
  flow_grid->setColumnStretch(0, 0);
  flow_grid->setColumnStretch(1, 1);
  flow_grid->setColumnStretch(2, 0);
  flow_grid->setColumnStretch(3, 1);

  g_max_segments = new QSpinBox(body);
  g_max_segments->setRange(1, 10);
  g_max_segments->setAlignment(Qt::AlignRight);
  g_max_segments->setToolTip(
      "Maximum visible segment units in this source box. "
      "If captions crowd or clip, lower Max Seg and/or font size.");
  g_max_chars = new QSpinBox(body);
  g_max_chars->setRange(50, 1000);
  g_max_chars->setSingleStep(10);
  g_max_chars->setAlignment(Qt::AlignRight);
  g_max_chars->setToolTip(
      "Maximum visible characters in this source box. "
      "Used with Max Seg; oldest lines are evicted when over budget.");
  add_grid_row(flow_grid, 0, body, "Max Seg", g_max_segments, "Max Chars", g_max_chars);

  g_auto_fit_text = new QCheckBox("Auto Fit Text To Box", body);
  g_auto_fit_text->setChecked(false);
  g_auto_fit_text->setEnabled(false);
  g_auto_fit_text->setToolTip("Deprecated: box resize affects margins only; font size is manual.");
  auto* auto_fit_spacer = new QLabel(" ", body);
  add_grid_row(flow_grid, 1, body, "", g_auto_fit_text, "", auto_fit_spacer);

  g_delay = new QSpinBox(body);
  g_delay->setRange(0, 90);
  g_delay->setAlignment(Qt::AlignRight);
  g_delay->setSuffix(" s");
  auto* delay_spacer = new QLabel(" ", body);
  add_grid_row(flow_grid, 2, body, "Delay", g_delay, "", delay_spacer);
  flow_content->addLayout(flow_grid);

  auto* type_section = new QFrame(body);
  type_section->setFrameShape(QFrame::StyledPanel);
  auto* type_layout = new QVBoxLayout(type_section);
  type_layout->setContentsMargins(8, 8, 8, 8);
  type_layout->setSpacing(6);
  auto* type_title = new QLabel("Typography", type_section);
  type_layout->addWidget(type_title);
  auto* style_target_row = new QHBoxLayout();
  style_target_row->setSpacing(6);
  auto* style_target_title = new QLabel("Style Target", type_section);
  style_target_title->setFixedWidth(kLabelWidth);
  g_style_target = new QComboBox(type_section);
  rebuild_style_target_items();
  g_style_target_label = new QLabel("Editing: all", type_section);
  g_style_target_label->setStyleSheet("color:#a6adba;");
  style_target_row->addWidget(style_target_title);
  style_target_row->addWidget(g_style_target, 0);
  style_target_row->addWidget(g_style_target_label, 1);
  type_layout->addLayout(style_target_row);

  auto* font_row = new QHBoxLayout();
  font_row->setSpacing(4);
  auto* font_label = new QLabel("Font", type_section);
  font_label->setFixedWidth(kLabelWidth);
  g_font_family = new QFontComboBox(type_section);
  g_font_family->setMinimumWidth(kFieldMinWidth);
  g_font_family->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  auto* size_label = new QLabel("Size", type_section);
  size_label->setFixedWidth(36);
  g_font_size = new QDoubleSpinBox(type_section);
  g_font_size->setRange(0.1, 40.0);
  g_font_size->setSingleStep(0.05);
  g_font_size->setDecimals(2);
  g_font_size->setAlignment(Qt::AlignRight);
  g_font_size->setSuffix(" px");
  g_font_size->setMinimumWidth(90);
  g_font_size->setToolTip(
      "Manual font size for this source box. "
      "If text overflows, reduce size or lower Max Seg.");
  g_font_size_slider = new QSlider(Qt::Horizontal, type_section);
  g_font_size_slider->setRange(2, 800);
  g_font_size_slider->setSingleStep(1);
  g_font_size_slider->setPageStep(5);
  g_font_size_slider->setMinimumWidth(96);
  font_row->addWidget(font_label);
  font_row->addWidget(g_font_family, 1);
  font_row->addWidget(size_label);
  font_row->addWidget(g_font_size);
  font_row->addWidget(g_font_size_slider, 1);
  type_layout->addLayout(font_row);

  auto* rendered_row = new QHBoxLayout();
  rendered_row->setSpacing(4);
  auto* rendered_label = new QLabel("Rendered", type_section);
  rendered_label->setFixedWidth(kLabelWidth);
  g_effective_font_size = new QLabel("Rendered: --", type_section);
  g_effective_font_size->setStyleSheet("color:#a6adba;");
  g_effective_font_size->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  g_use_rendered_as_base = new QPushButton("Use Rendered As Base", type_section);
  g_use_rendered_as_base->setToolTip("Copy current rendered size into the editable base font size.");
  rendered_row->addWidget(rendered_label);
  rendered_row->addWidget(g_effective_font_size, 1);
  rendered_row->addWidget(g_use_rendered_as_base);
  type_layout->addLayout(rendered_row);

  auto* color_row = new QHBoxLayout();
  color_row->setSpacing(6);
  color_row->setAlignment(Qt::AlignVCenter);
  auto* text_group = new QWidget(type_section);
  auto* text_group_row = new QHBoxLayout(text_group);
  text_group_row->setContentsMargins(0, 0, 0, 0);
  text_group_row->setSpacing(3);
  auto* text_label = new QLabel("Text", text_group);
  text_label->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
  g_text_color = new QPushButton(type_section);
  text_group_row->addWidget(text_label);
  text_group_row->addWidget(g_text_color);
  text_group->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);

  auto* text_opacity_wrap = new QWidget(type_section);
  auto* text_opacity_row = new QHBoxLayout(text_opacity_wrap);
  text_opacity_row->setContentsMargins(0, 0, 0, 0);
  text_opacity_row->setSpacing(4);
  g_text_opacity_value = new QLineEdit(text_opacity_wrap);
  g_text_opacity_value->setValidator(new QIntValidator(0, 100, g_text_opacity_value));
  g_text_opacity_value->setAlignment(Qt::AlignRight);
  g_text_opacity_value->setFixedWidth(44);
  g_text_opacity_slider = new QSlider(Qt::Horizontal, text_opacity_wrap);
  g_text_opacity_slider->setRange(0, 100);
  text_opacity_row->addWidget(g_text_opacity_value);
  text_opacity_row->addWidget(g_text_opacity_slider, 1);

  auto* bg_group = new QWidget(type_section);
  auto* bg_group_row = new QHBoxLayout(bg_group);
  bg_group_row->setContentsMargins(0, 0, 0, 0);
  bg_group_row->setSpacing(3);
  auto* bg_label = new QLabel("BG", bg_group);
  bg_label->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
  g_bg_color = new QPushButton(type_section);
  bg_group_row->addWidget(bg_label);
  bg_group_row->addWidget(g_bg_color);
  bg_group->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);

  auto* bg_opacity_wrap = new QWidget(type_section);
  auto* bg_opacity_row = new QHBoxLayout(bg_opacity_wrap);
  bg_opacity_row->setContentsMargins(0, 0, 0, 0);
  bg_opacity_row->setSpacing(4);
  g_bg_opacity_value = new QLineEdit(bg_opacity_wrap);
  g_bg_opacity_value->setValidator(new QIntValidator(0, 100, g_bg_opacity_value));
  g_bg_opacity_value->setAlignment(Qt::AlignRight);
  g_bg_opacity_value->setFixedWidth(44);
  g_bg_opacity_slider = new QSlider(Qt::Horizontal, bg_opacity_wrap);
  g_bg_opacity_slider->setRange(0, 100);
  bg_opacity_row->addWidget(g_bg_opacity_value);
  bg_opacity_row->addWidget(g_bg_opacity_slider, 1);

  color_row->addWidget(text_group, 0, Qt::AlignVCenter);
  color_row->addWidget(text_opacity_wrap, 1);
  color_row->addSpacing(6);
  color_row->addWidget(bg_group, 0, Qt::AlignVCenter);
  color_row->addWidget(bg_opacity_wrap, 1);
  type_layout->addLayout(color_row);

  auto* align_row = new QHBoxLayout();
  align_row->setSpacing(4);
  auto* align_label = new QLabel("Align", type_section);
  align_label->setFixedWidth(kLabelWidth);
  g_align_group = new QButtonGroup(type_section);
  g_align_left = new QToolButton(type_section);
  g_align_center = new QToolButton(type_section);
  g_align_right = new QToolButton(type_section);
  g_align_justify = new QToolButton(type_section);
  g_align_left->setText("▌▁▁");
  g_align_center->setText("▁▌▁");
  g_align_right->setText("▁▁▌");
  g_align_justify->setText("▔▔▔");
  g_align_left->setToolTip("Left align");
  g_align_center->setToolTip("Center align");
  g_align_right->setToolTip("Right align");
  g_align_justify->setToolTip("Justify align");
  for (QToolButton* button : {g_align_left, g_align_center, g_align_right, g_align_justify}) {
    button->setCheckable(true);
    button->setAutoRaise(false);
    QFont mono("Menlo");
    mono.setPointSize(10);
    button->setFont(mono);
    button->setMinimumHeight(28);
    button->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    button->setStyleSheet(
        "QToolButton{border:1px solid #666; border-radius:3px; padding:2px 4px;}"
        "QToolButton:checked{background:#3a4f76; border-color:#88aaff; color:white;}");
    g_align_group->addButton(button);
    align_row->addWidget(button);
  }
  g_align_group->setExclusive(true);
  align_row->insertWidget(0, align_label);
  type_layout->addLayout(align_row);

  g_preview = new QLabel("Preview: The quick brown fox jumps over the lazy dog.", type_section);
  g_preview->setWordWrap(true);
  g_preview->setMinimumHeight(64);
  type_layout->addWidget(g_preview);

  auto* live_row = new QHBoxLayout();
  auto* live_label = new QLabel("Live Output", type_section);
  g_live_output_count = new QLabel("0 chars", type_section);
  g_live_output_count->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
  g_live_output_count->setFixedWidth(180);
  g_live_colorize = new QCheckBox("Color Segments (Experimental)", type_section);
  g_live_colorize->setChecked(false);
  g_live_minimap = nullptr;
  live_row->addWidget(live_label);
  live_row->addSpacing(8);
  live_row->addWidget(g_live_colorize, 0, Qt::AlignVCenter);
  live_row->addStretch(1);
  live_row->addWidget(g_live_output_count, 0, Qt::AlignVCenter);
  type_layout->addLayout(live_row);
  g_live_output = new QTextEdit(type_section);
  g_live_output->setReadOnly(true);
  g_live_output->setLineWrapMode(QTextEdit::NoWrap);
  g_live_output->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  g_live_output->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  g_live_output->document()->setDocumentMargin(0.0);
  g_live_output_scroll = new QScrollArea(type_section);
  g_live_output_scroll->setWidgetResizable(false);
  g_live_output_scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  g_live_output_scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
  g_live_output_scroll->setFrameShape(QFrame::NoFrame);
  g_live_output_scroll->setWidget(g_live_output);
  g_live_output_scroll->setAlignment(Qt::AlignLeft | Qt::AlignTop);
  type_layout->addWidget(g_live_output_scroll);
  QObject::connect(g_live_output->horizontalScrollBar(), &QScrollBar::valueChanged, [](int) {
    update_live_minimap();
  });
  QObject::connect(g_live_output->verticalScrollBar(), &QScrollBar::valueChanged, [](int) {
    update_live_minimap();
  });
  QObject::connect(g_live_colorize, &QCheckBox::toggled, [](bool) {
    g_live_output_last_html.clear();
    const OverlayStateSnapshot snapshot = overlay_state_snapshot();
    if (!g_live_output) return;
    const QString html = make_live_output_html(snapshot);
    g_live_output->setHtml(html);
    g_live_output_last_html = html;
    update_live_minimap();
  });

  style_content->addWidget(type_section);
  setup_delayed_color_tooltip(g_text_color, &g_text_color_value);
  setup_delayed_color_tooltip(g_bg_color, &g_bg_color_value);

  QObject::connect(g_text_color, &QPushButton::clicked, [body]() {
    const QColor current = color_from_aarrggbb(g_text_color_value, QColor(255, 255, 255, 255));
    const QColor chosen = QColorDialog::getColor(
        current, body, "Text Color", QColorDialog::ShowAlphaChannel);
    if (!chosen.isValid()) return;
    g_text_color_value = color_to_aarrggbb(chosen);
    if (g_text_opacity_slider) {
      const int v = opacity_percent_from_aarrggbb(g_text_color_value, 100);
      g_text_opacity_slider->setValue(v);
      if (g_text_opacity_value) g_text_opacity_value->setText(QString::number(v));
    }
    set_color_button(g_text_color, g_text_color_value);
    update_preview();
    schedule_runtime_apply();
  });
  QObject::connect(g_bg_color, &QPushButton::clicked, [body]() {
    const QColor current = color_from_aarrggbb(g_bg_color_value, QColor(0, 0, 0, 0));
    const QColor chosen = QColorDialog::getColor(
        current, body, "Background Color", QColorDialog::ShowAlphaChannel);
    if (!chosen.isValid()) return;
    g_bg_color_value = color_to_aarrggbb(chosen);
    if (g_bg_opacity_slider) {
      const int v = opacity_percent_from_aarrggbb(g_bg_color_value, 0);
      g_bg_opacity_slider->setValue(v);
      if (g_bg_opacity_value) g_bg_opacity_value->setText(QString::number(v));
    }
    set_color_button(g_bg_color, g_bg_color_value);
    update_preview();
    schedule_runtime_apply();
  });
  QObject::connect(g_text_opacity_slider, &QSlider::valueChanged, [](int value) {
    if (g_text_opacity_value) g_text_opacity_value->setText(QString::number(value));
    g_text_color_value = set_aarrggbb_opacity(g_text_color_value, value);
    set_color_button(g_text_color, g_text_color_value);
    update_preview();
    schedule_runtime_apply();
  });
  QObject::connect(g_bg_opacity_slider, &QSlider::valueChanged, [](int value) {
    if (g_bg_opacity_value) g_bg_opacity_value->setText(QString::number(value));
    g_bg_color_value = set_aarrggbb_opacity(g_bg_color_value, value);
    set_color_button(g_bg_color, g_bg_color_value);
    update_preview();
    schedule_runtime_apply();
  });
  QObject::connect(g_text_opacity_value, &QLineEdit::editingFinished, []() {
    bool ok = false;
    const int value = g_text_opacity_value->text().toInt(&ok);
    g_text_opacity_slider->setValue(ok ? std::max(0, std::min(100, value)) : g_text_opacity_slider->value());
  });
  QObject::connect(g_bg_opacity_value, &QLineEdit::editingFinished, []() {
    bool ok = false;
    const int value = g_bg_opacity_value->text().toInt(&ok);
    g_bg_opacity_slider->setValue(ok ? std::max(0, std::min(100, value)) : g_bg_opacity_slider->value());
  });

  auto* window_grid = new QGridLayout();
  window_grid->setHorizontalSpacing(4);
  window_grid->setVerticalSpacing(6);
  window_grid->setColumnStretch(0, 0);
  window_grid->setColumnStretch(1, 1);
  window_grid->setColumnStretch(2, 0);
  window_grid->setColumnStretch(3, 1);

  g_width = new QSpinBox(body);
  g_width->setRange(100, 1920);
  g_width->setSingleStep(10);
  g_width->setAlignment(Qt::AlignRight);
  g_width->setSuffix(" px");
  g_height = new QSpinBox(body);
  g_height->setRange(60, 1080);
  g_height->setSingleStep(10);
  g_height->setAlignment(Qt::AlignRight);
  g_height->setSuffix(" px");
  add_grid_row(window_grid, 0, body, "Width", g_width, "Height", g_height);

  g_pad_x = new QSpinBox(body);
  g_pad_x->setRange(0, 2000);
  g_pad_x->setSingleStep(1);
  g_pad_x->setAlignment(Qt::AlignRight);
  g_pad_x->setSuffix(" px");
  g_pad_y = new QSpinBox(body);
  g_pad_y->setRange(0, 2000);
  g_pad_y->setSingleStep(1);
  g_pad_y->setAlignment(Qt::AlignRight);
  g_pad_y->setSuffix(" px");
  add_grid_row(window_grid, 1, body, "Pad X", g_pad_x, "Pad Y", g_pad_y);

  g_outline_enabled = new QCheckBox("On", body);
  g_outline_enabled->setChecked(true);
  g_outline_thickness = new QSpinBox(body);
  g_outline_thickness->setRange(1, 24);
  g_outline_thickness->setSingleStep(1);
  g_outline_thickness->setAlignment(Qt::AlignRight);
  g_outline_thickness->setSuffix(" px");
  add_grid_row(window_grid, 2, body, "Outline", g_outline_enabled, "Thickness", g_outline_thickness);

  auto* geom_mode = new QLabel("Linked Geometry (scene resize updates box)", body);
  geom_mode->setStyleSheet("color:#a6adba;");
  auto* geom_spacer = new QLabel(" ", body);
  add_grid_row(window_grid, 3, body, "", geom_mode, "", geom_spacer);
  window_content->addLayout(window_grid);

  g_animation_mode = new QComboBox(body);
  g_animation_mode->addItem("none");
  g_animation_mode->addItem("token_fade");
  g_animation_mode->addItem("line_roll");
  g_animation_mode->addItem("hybrid");
  auto* filler = new QLabel(" ", body);
  auto* animation_grid = new QGridLayout();
  animation_grid->setHorizontalSpacing(4);
  animation_grid->setVerticalSpacing(6);
  animation_grid->setColumnStretch(0, 0);
  animation_grid->setColumnStretch(1, 1);
  animation_grid->setColumnStretch(2, 0);
  animation_grid->setColumnStretch(3, 1);
  add_grid_row(animation_grid, 0, body, "Anim", g_animation_mode, "", filler);
  animation_content->addLayout(animation_grid);

  QObject::connect(g_font_family, &QFontComboBox::currentFontChanged, [](const QFont&) {
    update_preview();
    schedule_runtime_apply();
  });
  QObject::connect(g_font_size, &QDoubleSpinBox::valueChanged, [](double) {
    update_preview();
    schedule_runtime_apply();
  });
  QObject::connect(g_font_size, &QDoubleSpinBox::valueChanged, [](double value) {
    if (g_font_size_slider) g_font_size_slider->setValue(font_slider_from_value(value));
  });
  QObject::connect(g_font_size_slider, &QSlider::valueChanged, [](int value) {
    if (!g_font_size) return;
    const double mapped = font_value_from_slider(value);
    if (std::abs(g_font_size->value() - mapped) > 0.001) g_font_size->setValue(mapped);
  });
  QObject::connect(g_use_rendered_as_base, &QPushButton::clicked, []() {
    if (!g_font_size) return;
    const OverlayStateSnapshot snapshot = overlay_state_snapshot();
    const double effective = std::max(0.1, snapshot.effective_font_size_px);
    g_font_size->setValue(effective);
    if (g_font_size_slider) g_font_size_slider->setValue(font_slider_from_value(effective));
    schedule_runtime_apply();
  });
  QObject::connect(g_align_group, &QButtonGroup::buttonToggled,
                   [](QAbstractButton*, bool) {
                     update_preview();
                     schedule_runtime_apply();
                   });
  QObject::connect(g_width, &QSpinBox::valueChanged, [](int width) {
    if (!g_pad_x) return;
    const int max_pad = std::max(0, (width / 2) - 1);
    g_pad_x->setMaximum(max_pad);
    if (g_pad_x->value() > max_pad) g_pad_x->setValue(max_pad);
    apply_geometry_from_ui();
    schedule_runtime_apply();
  });
  QObject::connect(g_height, &QSpinBox::valueChanged, [](int height) {
    if (!g_pad_y) return;
    const int max_pad = std::max(0, (height / 2) - 1);
    g_pad_y->setMaximum(max_pad);
    if (g_pad_y->value() > max_pad) g_pad_y->setValue(max_pad);
    apply_geometry_from_ui();
    schedule_runtime_apply();
  });
  QObject::connect(g_max_segments, &QSpinBox::valueChanged, [](int) { schedule_runtime_apply(); });
  QObject::connect(g_max_chars, &QSpinBox::valueChanged, [](int) { schedule_runtime_apply(); });
  QObject::connect(g_auto_fit_text, &QCheckBox::toggled, [](bool) { schedule_runtime_apply(); });
  QObject::connect(g_delay, &QSpinBox::valueChanged, [](int) { schedule_runtime_apply(); });
  QObject::connect(g_pad_x, &QSpinBox::valueChanged, [](int) { schedule_runtime_apply(); });
  QObject::connect(g_pad_y, &QSpinBox::valueChanged, [](int) { schedule_runtime_apply(); });
  QObject::connect(g_outline_enabled, &QCheckBox::toggled, [](bool on) {
    if (g_outline_thickness) g_outline_thickness->setEnabled(on);
    schedule_runtime_apply();
  });
  QObject::connect(g_outline_thickness, &QSpinBox::valueChanged, [](int) { schedule_runtime_apply(); });
  QObject::connect(g_animation_mode, &QComboBox::currentTextChanged, [](const QString&) { schedule_runtime_apply(); });
  auto* actions = new QHBoxLayout();
  g_test_stream = new QPushButton("Test Stream: Off", body);
  g_test_stream->setCheckable(true);
  QObject::connect(g_test_stream, &QPushButton::clicked, []() {
    const bool active = g_test_stream->isChecked();
    g_test_stream->setProperty("active", active);
    g_test_stream->setText(active ? "Test Stream: On" : "Test Stream: Off");
    g_test_stream->setStyleSheet(active ? "QPushButton{background:#335a38;}" : "");
    schedule_runtime_apply();
  });
  auto* apply = new QPushButton("Apply", body);
  auto* revert = new QPushButton("Revert", body);
  QObject::connect(apply, &QPushButton::clicked, []() {
    const OverlayConfig cfg = collect_ui_config();
    overlay_state_set_config(cfg);
    persist_config_to_selected_source(cfg);
    const QString mode = QString::fromStdString(style_target_value()).toLower();
    if (mode == "all") {
      post_overlay_lane_update("mic", cfg);
      post_overlay_lane_update("desktop", cfg);
    } else if (mode == "mic" || mode == "desktop") {
      post_overlay_lane_update(mode, cfg);
    }
    blog(LOG_INFO, "what_overlay: qt panel apply");
  });
  QObject::connect(revert, &QPushButton::clicked, []() {
    load_snapshot_to_ui();
  });
  what_connect_check_state(g_source_mic_enabled, [](Qt::CheckState state) {
    const bool want_mic = state == Qt::Checked;
    const bool want_desktop = g_source_desktop_enabled && g_source_desktop_enabled->isChecked();
    apply_controller_stream_sources(want_mic, want_desktop);
  });
  what_connect_check_state(g_source_desktop_enabled, [](Qt::CheckState state) {
    const bool want_mic = g_source_mic_enabled && g_source_mic_enabled->isChecked();
    const bool want_desktop = state == Qt::Checked;
    apply_controller_stream_sources(want_mic, want_desktop);
  });
  what_connect_check_state(g_source_desktop_installed, [](Qt::CheckState state) {
    if (!g_source_desktop_installed) return;
    const bool installing = (state == Qt::Checked);
    g_source_desktop_installed->setEnabled(false);
    g_source_desktop_installed->setToolTip(installing ? "Installing desktop audio..." : "Uninstalling desktop audio...");
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    const QString base = controller_base_url_from_state();
    maybe_warmup_admin_auth(base);
    const QString path = installing
        ? QStringLiteral("/control/desktop-audio/install")
        : QStringLiteral("/control/desktop-audio/uninstall");
    const ControllerPostResult r = post_controller_json(base, path, QJsonObject{});
    blog(r.ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel desktop %s %s (HTTP %d %s)",
         installing ? "install" : "uninstall", r.ok ? "ok" : "failed",
         r.status_code, r.body.toUtf8().constData());
    if (!r.ok) {
      QSignalBlocker _b(g_source_desktop_installed);
      g_source_desktop_installed->setChecked(!installing);
    }
    g_source_desktop_installed->setEnabled(true);
    g_source_desktop_installed->setToolTip(g_source_desktop_installed->isChecked()
        ? "Desktop audio component installed — uncheck to uninstall"
        : "Desktop audio component not installed — check to install");
    refresh_controller_controls();
  });
  what_connect_check_state(g_box_mic_visible, [](Qt::CheckState state) {
    const bool visible = state == Qt::Checked;
    const bool with_label = g_box_mic_label && g_box_mic_label->isChecked();
    const bool ok = set_box_visibility_in_current_scene("mic", visible, with_label);
    blog(ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel %s mic box %s",
         visible ? "show" : "hide", ok ? "ok" : "failed");
    sync_geometry_from_scene_item();
  });
  what_connect_check_state(g_box_desktop_visible, [](Qt::CheckState state) {
    const bool visible = state == Qt::Checked;
    const bool with_label = g_box_desktop_label && g_box_desktop_label->isChecked();
    const bool ok = set_box_visibility_in_current_scene("desktop", visible, with_label);
    blog(ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel %s desktop box %s",
         visible ? "show" : "hide", ok ? "ok" : "failed");
    sync_geometry_from_scene_item();
  });
  what_connect_check_state(g_box_mic_label, [](Qt::CheckState state) {
    apply_header_for_source("mic", state == Qt::Checked);
    update_all_labels_state();
  });
  what_connect_check_state(g_box_desktop_label, [](Qt::CheckState state) {
    apply_header_for_source("desktop", state == Qt::Checked);
    update_all_labels_state();
  });
  what_connect_check_state(g_all_box_labels, [](Qt::CheckState state) {
    if (state == Qt::PartiallyChecked) return;
    const bool on = (state == Qt::Checked);
    if (g_box_mic_label) { QSignalBlocker _b(g_box_mic_label); g_box_mic_label->setChecked(on); }
    if (g_box_desktop_label) { QSignalBlocker _b(g_box_desktop_label); g_box_desktop_label->setChecked(on); }
    apply_headers_for_box_labels(on);
  });
  QObject::connect(g_style_target, &QComboBox::currentTextChanged, [](const QString& text) {
    if (g_style_target_label) {
      g_style_target_label->setText(QString("Editing: %1").arg(text.toLower()));
    }
    load_snapshot_to_ui();
  });
  actions->addWidget(g_test_stream);
  actions->addWidget(apply);
  actions->addWidget(revert);
  session_content->addLayout(actions);

  load_snapshot_to_ui();
  post_overlay_lane_updates_from_scene();
  body->setLayout(root);
  auto* container = new QVBoxLayout(window);
  container->setContentsMargins(0, 0, 0, 0);
  container->addWidget(body);
  window->setLayout(container);
  window->setMinimumWidth(360);
  if (window->layout()) window->layout()->activate();
  const int base_h = window->layout() ? window->layout()->sizeHint().height() : window->sizeHint().height();
  window->setMinimumHeight(base_h);
  window->resize(480, base_h);
  restore_panel_window_geometry(window);
  window->installEventFilter(new PanelWindowStateFilter(window, window));
  g_window = window;
  g_live_output_timer = new QTimer(window);
  g_live_output_timer->setInterval(100);
  QObject::connect(g_live_output_timer, &QTimer::timeout, []() {
    const OverlayStateSnapshot snapshot = overlay_state_snapshot();
    if (!g_live_output) return;
    if (g_effective_font_size) {
      g_effective_font_size->setText(
          QString("Rendered: %1 px").arg(snapshot.effective_font_size_px, 0, 'f', 2));
    }
    if (g_use_rendered_as_base) {
      g_use_rendered_as_base->setEnabled(snapshot.effective_font_size_px > 0.0);
    }
    const QString html = make_live_output_html(snapshot);
    if (g_live_output_last_html != html) {
      g_live_output->setHtml(html);
      g_live_output_last_html = html;
    }
    update_live_minimap();
    if (g_live_output_count) {
      const int char_count = static_cast<int>(QString::fromStdString(snapshot.rendered_text).size());
      const int seg_count = unique_visible_segment_count(snapshot);
      g_live_output_count->setText(QString("%1 chars | %2 seg").arg(char_count).arg(seg_count));
    }
  });
  g_live_output_timer->start();
  g_runtime_apply_timer = new QTimer(window);
  g_runtime_apply_timer->setSingleShot(true);
  g_runtime_apply_timer->setInterval(120);
  QObject::connect(g_runtime_apply_timer, &QTimer::timeout, []() {
    const OverlayConfig cfg = collect_ui_config();
    overlay_state_set_config(cfg);
    persist_config_to_selected_source(cfg);
    const QString mode = QString::fromStdString(style_target_value()).toLower();
    if (mode == "all") {
      post_overlay_lane_update("mic", cfg);
      post_overlay_lane_update("desktop", cfg);
    } else if (mode == "mic" || mode == "desktop") {
      post_overlay_lane_update(mode, cfg);
    }
  });
  auto* geometry_timer = new QTimer(window);
  geometry_timer->setInterval(40);
  QObject::connect(geometry_timer, &QTimer::timeout, []() {
    sync_geometry_from_scene_item();
    refresh_box_toggle_labels();
    sync_style_target_from_selected_source();
  });
  geometry_timer->start();
  auto* controller_timer = new QTimer(window);
  controller_timer->setInterval(1200);
  QObject::connect(controller_timer, &QTimer::timeout, []() { refresh_controller_controls(); });
  controller_timer->start();
  sync_geometry_from_scene_item();
  refresh_box_toggle_labels();
  sync_style_target_from_selected_source();
  refresh_controller_controls();
  persist_panel_window_geometry(window);
  blog(LOG_INFO, "what_overlay: qt window created");
}
#endif

static void toggle_panel_window() {
#if defined(WHAT_OVERLAY_HAS_QT_DOCK)
  ensure_dock();
  if (!g_window) return;
  const bool should_show = !g_window->isVisible();
  load_snapshot_to_ui();
  post_overlay_lane_updates_from_scene();
  g_window->setVisible(should_show);
  if (should_show) {
    g_window->raise();
    g_window->activateWindow();
  }
#else
  blog(LOG_INFO, "what_overlay: panel clicked (Qt dock not enabled in this build)");
#endif
}

struct NormalizeCtx {
  obs_sceneitem_t* selected_match = nullptr;
  obs_sceneitem_t* first_match = nullptr;
};

static bool find_what_scene_item(obs_scene_t* /*scene*/, obs_sceneitem_t* item, void* data) {
  auto* ctx = static_cast<NormalizeCtx*>(data);
  if (!ctx || !item) return true;
  obs_source_t* src = obs_sceneitem_get_source(item);
  if (!src) return true;
  const char* id = obs_source_get_id(src);
  if (!id || std::string(id) != "what_captions_source") return true;
  if (!ctx->first_match) ctx->first_match = item;
  if (obs_sceneitem_selected(item)) {
    ctx->selected_match = item;
    return false;
  }
  return true;
}

static bool resolve_target_what_scene_item(
    obs_source_t** out_scene_source, obs_sceneitem_t** out_item, obs_source_t** out_source) {
  if (out_scene_source) *out_scene_source = nullptr;
  if (out_item) *out_item = nullptr;
  if (out_source) *out_source = nullptr;
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return false;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return false;
  }
  NormalizeCtx ctx;
  obs_scene_enum_items(scene, find_what_scene_item, &ctx);
  obs_sceneitem_t* target_item = ctx.selected_match ? ctx.selected_match : ctx.first_match;
  if (!target_item) {
    obs_source_release(current_scene_src);
    return false;
  }
  obs_source_t* target = obs_sceneitem_get_source(target_item);
  if (!target) {
    obs_source_release(current_scene_src);
    return false;
  }
  if (out_scene_source) *out_scene_source = current_scene_src;
  if (out_item) *out_item = target_item;
  if (out_source) *out_source = target;
  return true;
}

static bool resolve_target_what_scene_item_for_mode(
    const std::string& mode,
    obs_source_t** out_scene_source,
    obs_sceneitem_t** out_item,
    obs_source_t** out_source) {
  if (mode != "mic" && mode != "desktop") {
    return resolve_target_what_scene_item(out_scene_source, out_item, out_source);
  }
  if (out_scene_source) *out_scene_source = nullptr;
  if (out_item) *out_item = nullptr;
  if (out_source) *out_source = nullptr;
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return false;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return false;
  }
  BoxSceneItemFindCtx ctx{mode, nullptr};
  obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
  if (!ctx.match) {
    obs_source_release(current_scene_src);
    return false;
  }
  obs_source_t* target = obs_sceneitem_get_source(ctx.match);
  if (!target) {
    obs_source_release(current_scene_src);
    return false;
  }
  if (out_scene_source) *out_scene_source = current_scene_src;
  if (out_item) *out_item = ctx.match;
  if (out_source) *out_source = target;
  return true;
}

static std::string box_from_source_settings(obs_source_t* source) {
  if (!source) return "";
  obs_data_t* settings = obs_source_get_settings(source);
  if (!settings) return "";
  const char* url_c = obs_data_get_string(settings, "url");
  const std::string url = url_c ? std::string(url_c) : std::string();
  obs_data_release(settings);
  const char* name_c = obs_source_get_name(source);
  const std::string name = name_c ? std::string(name_c) : std::string();
  return panel::detect_box_kind(url, name);
}

static bool find_what_scene_item_for_box(obs_scene_t* /*scene*/, obs_sceneitem_t* item, void* data) {
  auto* ctx = static_cast<BoxSceneItemFindCtx*>(data);
  if (!ctx || !item) return true;
  obs_source_t* src = obs_sceneitem_get_source(item);
  if (!src) return true;
  const char* id = obs_source_get_id(src);
  if (!id || std::string(id) != "what_captions_source") return true;
  const std::string box = box_from_source_settings(src);
  if (box == ctx->box) {
    ctx->match = item;
    return false;
  }
  return true;
}

static bool set_box_visibility_in_current_scene(const std::string& box, bool visible, bool with_labels) {
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return false;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return false;
  }

  BoxSceneItemFindCtx ctx{box, nullptr};
  obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
  if (ctx.match) {
    if (visible) {
      obs_sceneitem_set_visible(ctx.match, true);
      obs_sceneitem_select(ctx.match, true);
      obs_source_t* src = obs_sceneitem_get_source(ctx.match);
      if (src) {
        const std::string box_url = panel::box_events_url(box);
        obs_data_t* settings = obs_source_get_settings(src);
        obs_data_set_string(settings, "url", box_url.c_str());
        obs_data_set_string(settings, "control_url", "http://127.0.0.1:8780");
        const std::string header = panel::box_display_header(box, with_labels);
        obs_data_set_string(settings, "box_label", header.c_str());
        // Keep legacy header empty; box_label is the sole label control field.
        obs_data_set_string(settings, "header", "");
        obs_source_update(src, settings);
        obs_data_release(settings);
      }
      if (with_labels) {
        panel::SceneItemLabelState current{};
        obs_sceneitem_crop crop = {};
        obs_sceneitem_get_crop(ctx.match, &crop);
        vec2 pos = {};
        obs_sceneitem_get_pos(ctx.match, &pos);
        current.crop_top = crop.top;
        current.bounds_none = (obs_sceneitem_get_bounds_type(ctx.match) == OBS_BOUNDS_NONE);
        current.pos_y = pos.y;
        const panel::SceneItemLabelState normalized = panel::normalize_label_state_for_enable(current, 4.0f);
        if (crop.top != normalized.crop_top) {
          crop.top = normalized.crop_top;
          obs_sceneitem_set_crop(ctx.match, &crop);
        }
        if (!normalized.bounds_none) {
          obs_sceneitem_set_bounds_type(ctx.match, OBS_BOUNDS_NONE);
        } else if (obs_sceneitem_get_bounds_type(ctx.match) != OBS_BOUNDS_NONE) {
          obs_sceneitem_set_bounds_type(ctx.match, OBS_BOUNDS_NONE);
        }
        if (pos.y != normalized.pos_y) {
          pos.y = normalized.pos_y;
          obs_sceneitem_set_pos(ctx.match, &pos);
        }
      }
    } else {
      obs_sceneitem_set_visible(ctx.match, false);
    }
    obs_source_release(current_scene_src);
    return true;
  }

  if (!visible) {
    obs_source_release(current_scene_src);
    return true;
  }

  const OverlayStateSnapshot snap = overlay_state_snapshot();
  const std::string display_name = panel::box_display_header(box, true);
  const std::string title = "What Captions (" + (display_name.empty() ? box : display_name) + ")";
  const std::string box_url = panel::box_events_url(box);
  const std::string box_header = panel::box_display_header(box, with_labels);

  obs_data_t* settings = obs_data_create();
  obs_data_set_string(settings, "url", box_url.c_str());
  obs_data_set_string(settings, "control_url", "http://127.0.0.1:8780");
  obs_data_set_string(settings, "box_label", box_header.c_str());
  // Keep legacy header empty; box_label is the sole label control field.
  obs_data_set_string(settings, "header", "");
  obs_data_set_int(settings, "max_segments", snap.config.max_segments);
  obs_data_set_int(settings, "max_chars", snap.config.max_chars);
  obs_data_set_double(settings, "font_size", snap.config.font_size_px);
  obs_data_set_int(settings, "width", snap.config.width_px);
  obs_data_set_int(settings, "height", snap.config.height_px);
  obs_data_set_int(settings, "pad_x", snap.config.padding_x_px);
  obs_data_set_int(settings, "pad_y", snap.config.padding_y_px);
  obs_data_set_bool(settings, "outline_enabled", snap.config.outline_enabled);
  obs_data_set_int(settings, "outline_thickness_px", std::max(1, std::min(24, snap.config.outline_thickness_px)));
  obs_data_set_string(settings, "align", snap.config.align.c_str());
  obs_data_set_string(settings, "animation_mode", snap.config.animation_mode.c_str());
  obs_data_set_bool(settings, "no_word_split", snap.config.no_word_split);
  obs_data_set_string(settings, "text_color", snap.config.text_color.c_str());
  obs_data_set_string(settings, "bg_color", snap.config.bg_color.c_str());
  obs_data_t* font = obs_data_create();
  obs_data_set_string(font, "face", snap.config.font_family.c_str());
  obs_data_set_obj(settings, "font", font);
  obs_data_release(font);
  obs_source_t* source = obs_source_create("what_captions_source", title.c_str(), settings, nullptr);
  obs_data_release(settings);
  if (!source) {
    obs_source_release(current_scene_src);
    return false;
  }
  obs_sceneitem_t* item = obs_scene_add(scene, source);
  if (item) {
    obs_sceneitem_set_visible(item, true);
    obs_sceneitem_select(item, true);
  }
  obs_source_release(source);
  obs_source_release(current_scene_src);
  return item != nullptr;
}

static bool is_box_visible_in_current_scene(const std::string& box) {
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return false;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return false;
  }
  BoxSceneItemFindCtx ctx{box, nullptr};
  obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
  bool visible = false;
  if (ctx.match) {
    visible = obs_sceneitem_visible(ctx.match);
  }
  obs_source_release(current_scene_src);
  return visible;
}

static std::string selected_box_in_current_scene() {
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return "";
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return "";
  }
  NormalizeCtx ctx;
  obs_scene_enum_items(scene, find_what_scene_item, &ctx);
  obs_sceneitem_t* target_item = ctx.selected_match;
  if (!target_item) {
    obs_source_release(current_scene_src);
    return "";
  }
  obs_source_t* target = obs_sceneitem_get_source(target_item);
  const std::string box = box_from_source_settings(target);
  obs_source_release(current_scene_src);
  return box;
}

static void apply_header_for_source(const std::string& box, bool with_label) {
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return;
  }
  BoxSceneItemFindCtx ctx{box, nullptr};
  obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
  if (ctx.match) {
    obs_source_t* src = obs_sceneitem_get_source(ctx.match);
    if (src) {
      obs_data_t* settings = obs_source_get_settings(src);
      const std::string header = panel::box_display_header(box, with_label);
      // `box_label` is dedicated header-render metadata for the overlay source.
      // Keep legacy `header` empty so no downstream path can treat it as body text.
      obs_data_set_string(settings, "box_label", header.c_str());
      obs_data_set_string(settings, "header", "");
      obs_source_update(src, settings);
      obs_data_release(settings);
      if (with_label) {
        panel::SceneItemLabelState current{};
        obs_sceneitem_crop crop = {};
        obs_sceneitem_get_crop(ctx.match, &crop);
        vec2 pos = {};
        obs_sceneitem_get_pos(ctx.match, &pos);
        current.crop_top = crop.top;
        current.bounds_none = (obs_sceneitem_get_bounds_type(ctx.match) == OBS_BOUNDS_NONE);
        current.pos_y = pos.y;
        const panel::SceneItemLabelState normalized = panel::normalize_label_state_for_enable(current, 4.0f);
        if (crop.top != normalized.crop_top) {
          crop.top = normalized.crop_top;
          obs_sceneitem_set_crop(ctx.match, &crop);
        }
        if (!normalized.bounds_none) {
          obs_sceneitem_set_bounds_type(ctx.match, OBS_BOUNDS_NONE);
        } else if (obs_sceneitem_get_bounds_type(ctx.match) != OBS_BOUNDS_NONE) {
          obs_sceneitem_set_bounds_type(ctx.match, OBS_BOUNDS_NONE);
        }
        if (pos.y != normalized.pos_y) {
          pos.y = normalized.pos_y;
          obs_sceneitem_set_pos(ctx.match, &pos);
        }
      }
    }
  }
  obs_source_release(current_scene_src);
}

static void apply_headers_for_box_labels(bool with_labels) {
  for (const std::string& box : g_active_sources) {
    apply_header_for_source(box, with_labels);
  }
}

static void update_all_labels_state() {
  if (!g_all_box_labels) return;
  const bool mic_on = !g_box_mic_label || g_box_mic_label->isChecked();
  const bool desktop_on = !g_box_desktop_label || g_box_desktop_label->isChecked();
  QSignalBlocker _b(g_all_box_labels);
  if (mic_on && desktop_on) {
    g_all_box_labels->setCheckState(Qt::Checked);
  } else if (!mic_on && !desktop_on) {
    g_all_box_labels->setCheckState(Qt::Unchecked);
  } else {
    g_all_box_labels->setCheckState(Qt::PartiallyChecked);
  }
}

static std::string style_target_value() {
  if (!g_style_target) return "all";
  const QString v = g_style_target->currentData().toString();
  const std::string s = v.toStdString();
  if (s == "mic" || s == "desktop" || s == "all") return s;
  return "all";
}

static void sync_style_target_from_selected_source() {
  if (!g_style_target || !g_style_target_label) return;
  const std::string box = selected_box_in_current_scene();
  if (box != "mic" && box != "desktop") return;
  const QString target = QString::fromStdString(box);
  const int idx = g_style_target->findData(target);
  if (idx >= 0 && g_style_target->currentIndex() != idx) {
    g_style_target->setCurrentIndex(idx);
  }
  g_style_target_label->setText(QString("Editing: %1").arg(target));
}

static void refresh_box_toggle_labels() {
  if (g_box_mic_visible) {
    QSignalBlocker _b(g_box_mic_visible);
    g_box_mic_visible->setChecked(is_box_visible_in_current_scene("mic"));
  }
  if (g_box_desktop_visible) {
    QSignalBlocker _b(g_box_desktop_visible);
    g_box_desktop_visible->setChecked(is_box_visible_in_current_scene("desktop"));
  }
}

static void rebuild_style_target_items() {
  if (!g_style_target) return;
  const QString current = g_style_target->currentData().toString();
  g_style_target->blockSignals(true);
  g_style_target->clear();
  for (const std::string& box : g_active_sources) {
    const std::string display = panel::box_display_header(box, true);
    g_style_target->addItem(QString::fromStdString(display.empty() ? box : display),
                            QString::fromStdString(box));
  }
  g_style_target->addItem("All", "all");
  const int idx = g_style_target->findData(current);
  g_style_target->setCurrentIndex(idx >= 0 ? idx : g_style_target->count() - 1);
  g_style_target->blockSignals(false);
}

static void sync_geometry_from_scene_item() {
  if (!g_width || !g_height) return;
  obs_source_t* scene_src = nullptr;
  obs_sceneitem_t* item = nullptr;
  obs_source_t* source = nullptr;
  const std::string target_mode = style_target_value();
  if (!resolve_target_what_scene_item_for_mode(target_mode, &scene_src, &item, &source)) {
    if (g_geometry_status) g_geometry_status->setText("Geometry: Unlinked");
    return;
  }
  const uint32_t source_w = obs_source_get_width(source);
  const uint32_t source_h = obs_source_get_height(source);
  struct vec2 scale = {1.0f, 1.0f};
  obs_sceneitem_get_scale(item, &scale);
  int display_w = std::max(1, static_cast<int>(std::lround(source_w * std::abs(scale.x))));
  int display_h = std::max(1, static_cast<int>(std::lround(source_h * std::abs(scale.y))));
  const obs_bounds_type bounds_type = obs_sceneitem_get_bounds_type(item);
  if (bounds_type != OBS_BOUNDS_NONE) {
    struct vec2 bounds = {0.0f, 0.0f};
    obs_sceneitem_get_bounds(item, &bounds);
    if (bounds.x > 0.0f) display_w = std::max(1, static_cast<int>(std::lround(bounds.x)));
    if (bounds.y > 0.0f) display_h = std::max(1, static_cast<int>(std::lround(bounds.y)));
  }
  // Authoritative body geometry comes from source settings. Scene/render
  // dimensions include dynamic extras (e.g. label strip), which can cause
  // width->height feedback drift when mirrored back into settings.
  int body_w = std::max(100, display_w);
  int body_h = std::max(60, display_h);
  obs_data_t* source_settings = obs_source_get_settings(source);
  if (source_settings) {
    const int cfg_w = static_cast<int>(obs_data_get_int(source_settings, "width"));
    const int cfg_h = static_cast<int>(obs_data_get_int(source_settings, "height"));
    if (cfg_w > 0) body_w = std::max(100, cfg_w);
    if (cfg_h > 0) body_h = std::max(60, cfg_h);
    obs_data_release(source_settings);
  }
  g_syncing_geometry = true;
  const bool width_signals = g_width->blockSignals(true);
  const bool height_signals = g_height->blockSignals(true);
  g_width->setValue(body_w);
  g_height->setValue(body_h);
  g_width->blockSignals(width_signals);
  g_height->blockSignals(height_signals);
  g_syncing_geometry = false;
  const OverlayStateSnapshot snap = overlay_state_snapshot();
  if (target_mode == "all") {
    publish_overlay_geometry_to_controller_if_changed(
        body_w, body_h, snap.config.padding_x_px, snap.config.font_size_px);
  }
  if (g_geometry_status) g_geometry_status->setText("Geometry: Linked");
  obs_source_release(scene_src);
}

static void apply_geometry_from_ui() {
  if (!g_width || !g_height || g_syncing_geometry) return;
  obs_source_t* scene_src = nullptr;
  obs_sceneitem_t* item = nullptr;
  obs_source_t* source = nullptr;
  const std::string target_mode = style_target_value();
  if (!resolve_target_what_scene_item_for_mode(target_mode, &scene_src, &item, &source)) {
    if (g_geometry_status) g_geometry_status->setText("Geometry: Unlinked");
    return;
  }

  const int width = std::max(100, g_width->value());
  const int height = std::max(60, g_height->value());
  obs_data_t* settings = obs_source_get_settings(source);
  obs_data_set_int(settings, "width", width);
  obs_data_set_int(settings, "height", height);
  obs_source_update(source, settings);
  obs_data_release(settings);
  const OverlayStateSnapshot snap = overlay_state_snapshot();
  overlay_state_set_geometry(width, height, snap.config.padding_x_px, snap.config.padding_y_px);

  struct vec2 scale = {1.0f, 1.0f};
  obs_sceneitem_set_scale(item, &scale);
  obs_sceneitem_set_bounds_type(item, OBS_BOUNDS_NONE);
  if (g_geometry_status) g_geometry_status->setText("Geometry: Linked");
  obs_source_release(scene_src);
}

static void persist_config_to_selected_source(const OverlayConfig& cfg) {
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return;
  }

  auto apply_to_source = [&](obs_source_t* target) {
    if (!target) return;
    obs_data_t* settings = obs_source_get_settings(target);
    obs_data_set_int(settings, "max_segments", cfg.max_segments);
    obs_data_set_int(settings, "max_chars", cfg.max_chars);
    obs_data_set_double(settings, "font_size", cfg.font_size_px);
    obs_data_set_bool(settings, "auto_shrink_to_fit", cfg.auto_shrink_to_fit);
    obs_data_set_int(settings, "delay_seconds", cfg.delay_seconds);
    obs_data_set_int(settings, "width", cfg.width_px);
    obs_data_set_int(settings, "height", cfg.height_px);
    obs_data_set_int(settings, "pad_x", cfg.padding_x_px);
    obs_data_set_int(settings, "pad_y", cfg.padding_y_px);
    obs_data_set_bool(settings, "outline_enabled", cfg.outline_enabled);
    obs_data_set_int(settings, "outline_thickness_px", std::max(1, std::min(24, cfg.outline_thickness_px)));
    obs_data_set_string(settings, "align", cfg.align.c_str());
    obs_data_set_string(settings, "animation_mode", cfg.animation_mode.c_str());
    obs_data_set_bool(settings, "test_stream", cfg.test_stream);
    obs_data_set_bool(settings, "no_word_split", cfg.no_word_split);
    obs_data_set_string(settings, "text_color", cfg.text_color.c_str());
    obs_data_set_string(settings, "bg_color", cfg.bg_color.c_str());
    obs_data_t* font = obs_data_create();
    obs_data_set_string(font, "face", cfg.font_family.c_str());
    obs_data_set_obj(settings, "font", font);
    obs_data_release(font);
    obs_source_update(target, settings);
    obs_data_release(settings);
  };

  const std::string target_mode = style_target_value();
  if (target_mode == "all") {
    for (const std::string& box : g_active_sources) {
      BoxSceneItemFindCtx ctx{box, nullptr};
      obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
      if (!ctx.match) continue;
      apply_to_source(obs_sceneitem_get_source(ctx.match));
    }
  } else {
    BoxSceneItemFindCtx ctx{target_mode, nullptr};
    obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
    if (ctx.match) {
      apply_to_source(obs_sceneitem_get_source(ctx.match));
    }
  }

  // Test stream is runtime-global in practice; keep both box sources aligned
  // so one source cannot immediately cancel the other. Only write when the
  // persisted value actually changes to avoid noisy runtime churn.
  bool test_stream_changed = false;
  for (const std::string& box : g_active_sources) {
    BoxSceneItemFindCtx ctx{box, nullptr};
    obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
    if (!ctx.match) continue;
    obs_source_t* target = obs_sceneitem_get_source(ctx.match);
    if (!target) continue;
    obs_data_t* settings = obs_source_get_settings(target);
    const bool current = obs_data_get_bool(settings, "test_stream");
    if (current != cfg.test_stream) {
      obs_data_set_bool(settings, "test_stream", cfg.test_stream);
      obs_source_update(target, settings);
      test_stream_changed = true;
    }
    obs_data_release(settings);
  }
  if (test_stream_changed) {
    blog(LOG_INFO, "what_overlay: panel_apply_test_stream enabled=%s target_mode=%s",
         cfg.test_stream ? "true" : "false", target_mode.c_str());
  }
  obs_source_release(current_scene_src);
}

static void post_overlay_lane_update_from_scene(const QString& lane) {
  const QString lane_norm = lane.trimmed().toLower();
  if (lane_norm != "mic" && lane_norm != "desktop") return;
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) return;
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    return;
  }
  BoxSceneItemFindCtx ctx{lane_norm.toStdString(), nullptr};
  obs_scene_enum_items(scene, find_what_scene_item_for_box, &ctx);
  if (!ctx.match) {
    obs_source_release(current_scene_src);
    return;
  }
  obs_source_t* target = obs_sceneitem_get_source(ctx.match);
  if (!target) {
    obs_source_release(current_scene_src);
    return;
  }
  obs_data_t* settings = obs_source_get_settings(target);
  OverlayConfig cfg = overlay_state_snapshot().config;
  cfg.max_segments = static_cast<int>(obs_data_get_int(settings, "max_segments"));
  cfg.max_chars = static_cast<int>(obs_data_get_int(settings, "max_chars"));
  cfg.width_px = static_cast<int>(obs_data_get_int(settings, "width"));
  cfg.height_px = static_cast<int>(obs_data_get_int(settings, "height"));
  cfg.padding_x_px = static_cast<int>(obs_data_get_int(settings, "pad_x"));
  cfg.font_size_px = static_cast<double>(obs_data_get_double(settings, "font_size"));
  obs_data_release(settings);
  post_overlay_lane_update(lane_norm, cfg);
  obs_source_release(current_scene_src);
}

static void post_overlay_lane_updates_from_scene() {
  post_overlay_lane_update_from_scene("mic");
  post_overlay_lane_update_from_scene("desktop");
}

static void normalize_selected_what_scene_item() {
  obs_source_t* current_scene_src = obs_frontend_get_current_scene();
  if (!current_scene_src) {
    blog(LOG_WARNING, "what_overlay: normalize failed (no current scene)");
    return;
  }
  obs_scene_t* scene = obs_scene_from_source(current_scene_src);
  if (!scene) {
    obs_source_release(current_scene_src);
    blog(LOG_WARNING, "what_overlay: normalize failed (current source is not a scene)");
    return;
  }

  NormalizeCtx ctx;
  obs_scene_enum_items(scene, find_what_scene_item, &ctx);
  obs_sceneitem_t* target = ctx.selected_match ? ctx.selected_match : ctx.first_match;
  if (!target) {
    obs_source_release(current_scene_src);
    blog(LOG_WARNING, "what_overlay: normalize skipped (no what_captions_source item in scene)");
    return;
  }

  obs_source_t* source = obs_sceneitem_get_source(target);
  const uint32_t source_w = source ? obs_source_get_width(source) : 0;
  const uint32_t source_h = source ? obs_source_get_height(source) : 0;
  struct vec2 prev_scale = {1.0f, 1.0f};
  obs_sceneitem_get_scale(target, &prev_scale);
  const int display_w =
      std::max(100, static_cast<int>(std::lround(static_cast<double>(source_w) * std::abs(prev_scale.x))));
  const int display_h =
      std::max(60, static_cast<int>(std::lround(static_cast<double>(source_h) * std::abs(prev_scale.y))));

  if (source) {
    obs_data_t* settings = obs_source_get_settings(source);
    obs_data_set_int(settings, "width", display_w);
    obs_data_set_int(settings, "height", display_h);
    obs_source_update(source, settings);
    obs_data_release(settings);
  }

  struct vec2 scale = {1.0f, 1.0f};
  obs_sceneitem_set_scale(target, &scale);
  obs_sceneitem_set_bounds_type(target, OBS_BOUNDS_NONE);
  obs_source_release(current_scene_src);
  sync_geometry_from_scene_item();
  blog(LOG_INFO, "what_overlay: normalized scene item transform (preserve size %dx%d)", display_w, display_h);
}

void on_tools_menu(void* /*private_data*/) {
  toggle_panel_window();
}

}  // namespace

void init_overlay_panel() {
  if (g_registered) return;
#if defined(WHAT_OVERLAY_HAS_QT_DOCK)
  g_tools_action = static_cast<QAction*>(obs_frontend_add_tools_menu_qaction(kMenuLabel));
  if (g_tools_action) {
    g_tools_action->setShortcut(QKeySequence(QStringLiteral("Ctrl+Alt+W")));
    g_tools_action->setShortcutContext(Qt::ApplicationShortcut);
    QObject::connect(g_tools_action, &QAction::triggered, []() { toggle_panel_window(); });
  } else {
    obs_frontend_add_tools_menu_item(kMenuLabel, on_tools_menu, nullptr);
  }
#else
  obs_frontend_add_tools_menu_item(kMenuLabel, on_tools_menu, nullptr);
#endif
  g_registered = true;
  blog(LOG_INFO, "what_overlay: frontend panel scaffold registered");
}

void shutdown_overlay_panel() {
#if defined(WHAT_OVERLAY_HAS_QT_DOCK)
  {
    const QString base = controller_base_url_from_state();
    const ControllerPostResult r = post_controller_json(base, "/control/desktop-audio/uninstall", QJsonObject{});
    blog(r.ok ? LOG_INFO : LOG_WARNING, "what_overlay: panel shutdown desktop uninstall %s (HTTP %d %s)",
         r.ok ? "ok" : "failed", r.status_code, r.body.toUtf8().constData());
  }
  g_tools_action = nullptr;
  if (g_window) {
    persist_panel_window_geometry(g_window);
    g_window->close();
    g_window->deleteLater();
    g_window = nullptr;
  }
  g_source_mic_enabled = nullptr;
  g_source_desktop_enabled = nullptr;
  g_source_desktop_installed = nullptr;
  g_per_app_audio_combo = nullptr;
  g_admin_warmup_done = false;
  g_box_mic_visible = nullptr;
  g_box_desktop_visible = nullptr;
  g_box_mic_label = nullptr;
  g_box_desktop_label = nullptr;
  g_all_box_labels = nullptr;
  g_style_target = nullptr;
  g_style_target_label = nullptr;
  g_controller_status = nullptr;
  g_geometry_status = nullptr;
  g_max_segments = nullptr;
  g_max_chars = nullptr;
  g_font_size = nullptr;
  g_effective_font_size = nullptr;
  g_use_rendered_as_base = nullptr;
  g_auto_fit_text = nullptr;
  g_delay = nullptr;
  g_width = nullptr;
  g_height = nullptr;
  g_pad_x = nullptr;
  g_pad_y = nullptr;
  g_outline_enabled = nullptr;
  g_outline_thickness = nullptr;
  g_align_group = nullptr;
  g_align_left = nullptr;
  g_align_center = nullptr;
  g_align_right = nullptr;
  g_align_justify = nullptr;
  g_font_family = nullptr;
  g_animation_mode = nullptr;
  g_test_stream = nullptr;
  g_text_color = nullptr;
  g_bg_color = nullptr;
  g_text_opacity_slider = nullptr;
  g_bg_opacity_slider = nullptr;
  g_text_opacity_value = nullptr;
  g_bg_opacity_value = nullptr;
  g_font_size_slider = nullptr;
  g_preview = nullptr;
  g_live_output_count = nullptr;
  g_live_output = nullptr;
  g_live_output_scroll = nullptr;
  g_live_output_timer = nullptr;
  g_runtime_apply_timer = nullptr;
  g_live_colorize = nullptr;
  g_live_minimap = nullptr;
  g_live_output_last_html.clear();
#endif
  g_registered = false;
}

}  // namespace what_overlay
