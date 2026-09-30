#include "what_overlay/pipeline/transition_policy.h"

namespace what_overlay::pipeline {

TransitionLineRelationship compute_line_relationship(const std::vector<std::string>& prev_lines,
                                                     const std::vector<std::string>& next_lines) {
  TransitionLineRelationship out;

  if (prev_lines.size() >= 2 && prev_lines.size() == next_lines.size()) {
    out.strict_roll = true;
    for (size_t i = 0; i + 1 < prev_lines.size(); ++i) {
      if (prev_lines[i + 1] != next_lines[i]) {
        out.strict_roll = false;
        break;
      }
    }
    if (out.strict_roll && !prev_lines.empty() && prev_lines.back() == next_lines.back()) {
      out.strict_roll = false;
    }
  }

  if (next_lines.size() == prev_lines.size() + 1 && !prev_lines.empty()) {
    out.grow_append = true;
    for (size_t i = 0; i < prev_lines.size(); ++i) {
      if (prev_lines[i] != next_lines[i]) {
        out.grow_append = false;
        break;
      }
    }
  }

  return out;
}

TransitionDecision decide_transition(const TransitionDecisionInput& input) {
  TransitionDecision out;
  out.strict_roll = input.strict_roll;
  out.grow_append = input.grow_append;

  if (input.disable_animation) {
    out.shift_prev = out.strict_roll;
    return out;
  }

  const bool hint_roll = input.transition_hint == "roll";
  const bool hint_grow = input.transition_hint == "grow";
  const bool use_hint = input.allow_transition_hints &&
                        (hint_roll || hint_grow || input.transition_hint == "none");

  if (input.animation_mode == "token_fade") {
    out.animate = input.has_prev && input.visible_changed && !input.currently_animating;
    out.fade_only = out.animate;
  } else if (input.animation_mode == "none") {
    out.animate = false;
  } else if (use_hint) {
    out.animate = input.has_prev && input.visible_changed &&
                  (hint_roll || hint_grow) && !input.currently_animating;
    out.strict_roll = hint_roll;
    out.grow_append = hint_grow;
  } else {
    out.animate = input.has_prev && input.visible_changed &&
                  (out.strict_roll || out.grow_append) && !input.currently_animating;
  }

  out.shift_prev = out.strict_roll;
  return out;
}

}  // namespace what_overlay::pipeline
