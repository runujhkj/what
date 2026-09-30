const constraintsAuthority = require("./overlay_constraints_authority");

function createSetOverlayTestStreamEnabled(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const setConstraints = typeof ctx.setConstraints === "function" ? ctx.setConstraints : () => {};
  const setEnabled = typeof ctx.setEnabled === "function" ? ctx.setEnabled : () => {};
  const coerceEnabled = typeof ctx.coerceEnabled === "function" ? ctx.coerceEnabled : Boolean;

  return function setOverlayTestStreamEnabled(enabled) {
    if (enabled && typeof enabled === "object") {
      const normalizedBox = constraintsAuthority.normalizeBoxKey(enabled.box);
      const patchOut = constraintsAuthority.buildConstraintPatch({
        ...enabled,
        box: normalizedBox,
      });
      if (patchOut.hasConstraintPatch) {
        setConstraints(patchOut.patch);
      }
      setEnabled(coerceEnabled(enabled.enabled), normalizedBox);
      return;
    }
    setEnabled(coerceEnabled(enabled));
  };
}

module.exports = {
  createSetOverlayTestStreamEnabled,
};
