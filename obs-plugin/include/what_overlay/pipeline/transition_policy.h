#pragma once

#include <string>
#include <vector>

namespace what_overlay::pipeline {

struct TransitionLineRelationship {
  bool strict_roll = false;
  bool grow_append = false;
};

TransitionLineRelationship compute_line_relationship(const std::vector<std::string>& prev_lines,
                                                     const std::vector<std::string>& next_lines);

struct TransitionDecisionInput {
  bool has_prev = false;
  bool visible_changed = false;
  bool currently_animating = false;
  std::string animation_mode;
  std::string transition_hint;
  bool strict_roll = false;
  bool grow_append = false;
  bool allow_transition_hints = false;
  bool disable_animation = false;
};

struct TransitionDecision {
  bool animate = false;
  bool fade_only = false;
  bool shift_prev = false;
  bool strict_roll = false;
  bool grow_append = false;
};

TransitionDecision decide_transition(const TransitionDecisionInput& input);

}  // namespace what_overlay::pipeline
