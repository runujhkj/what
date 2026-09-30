#include "what_overlay/pipeline/transition_policy.h"

#include <cassert>
#include <vector>

using what_overlay::pipeline::TransitionDecisionInput;
using what_overlay::pipeline::compute_line_relationship;
using what_overlay::pipeline::decide_transition;

int main() {
  {
    const auto rel = compute_line_relationship(
        {"a", "b", "c"},
        {"b", "c", "d"});
    assert(rel.strict_roll);
    assert(!rel.grow_append);
  }

  {
    const auto rel = compute_line_relationship(
        {"a", "b"},
        {"a", "b", "c"});
    assert(!rel.strict_roll);
    assert(rel.grow_append);
  }

  {
    TransitionDecisionInput in{};
    in.has_prev = true;
    in.visible_changed = true;
    in.animation_mode = "token_fade";
    const auto out = decide_transition(in);
    assert(out.animate);
    assert(out.fade_only);
  }

  {
    TransitionDecisionInput in{};
    in.has_prev = true;
    in.visible_changed = true;
    in.animation_mode = "roll";
    in.strict_roll = true;
    const auto out = decide_transition(in);
    assert(out.animate);
    assert(!out.fade_only);
    assert(out.shift_prev);
  }

  {
    TransitionDecisionInput in{};
    in.has_prev = true;
    in.visible_changed = true;
    in.animation_mode = "roll";
    in.allow_transition_hints = true;
    in.transition_hint = "grow";
    const auto out = decide_transition(in);
    assert(out.animate);
    assert(!out.strict_roll);
    assert(out.grow_append);
  }

  {
    TransitionDecisionInput in{};
    in.has_prev = true;
    in.visible_changed = true;
    in.animation_mode = "token_fade";
    in.disable_animation = true;
    const auto out = decide_transition(in);
    assert(!out.animate);
    assert(!out.fade_only);
  }

  return 0;
}
