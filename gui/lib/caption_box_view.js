// Keep sealed line elements alive; animate positions, never rebuild their words.
function createCaptionView(container, { lineHeight, duration = 180, reducedMotion = false }) {
  const nodes = new Map();
  const retiring = new Set();
  function remove(entry) {
    if (entry.animation) entry.animation.cancel();
    entry.element.remove();
    retiring.delete(entry);
  }
  function move(entry, y, animate) {
    const element = entry.element;
    const from = entry.animation && typeof element.getBoundingClientRect === 'function'
      ? element.getBoundingClientRect().top - container.getBoundingClientRect().top : entry.y;
    if (entry.animation) entry.animation.cancel();
    entry.y = y;
    element.style.transform = `translateY(${y}px)`;
    entry.animation = null;
    if (animate && from !== y && typeof element.animate === 'function') {
      entry.animation = element.animate([
        { transform: `translateY(${from}px)` }, { transform: `translateY(${y}px)` },
      ], { duration, easing: 'ease-out' });
    }
  }
  function render(rows, { reset = false } = {}) {
    const animate = !reset && !reducedMotion && duration > 0;
    if (reset) {
      for (const entry of retiring) remove(entry);
    }
    const retained = rows.findIndex(row => nodes.has(row.id));
    const shift = retained >= 0
      ? Math.max(0, nodes.get(rows[retained].id).y - retained * lineHeight)
      : (nodes.size ? nodes.size * lineHeight : 0);
    const ids = new Set(rows.map(row => row.id));
    for (const [id, entry] of nodes) {
      if (ids.has(id)) continue;
      nodes.delete(id);
      if (animate && shift && rows.length) {
        move(entry, entry.y - shift, true);
        if (entry.animation) {
          retiring.add(entry);
          entry.animation.onfinish = () => remove(entry);
          continue;
        }
      }
      remove(entry);
    }
    rows.forEach((row, index) => {
      const y = index * lineHeight;
      let entry = nodes.get(row.id);
      if (!entry) {
        const element = container.ownerDocument.createElement('div');
        element.className = 'caption-line';
        entry = { element, y: y + (animate ? shift : 0), animation: null };
        nodes.set(row.id, entry);
        container.appendChild(element);
        element.style.transform = `translateY(${entry.y}px)`;
      }
      if (entry.element.textContent !== row.text) entry.element.textContent = row.text;
      if (entry.y !== y || reset) move(entry, y, animate);
    });
    if (!rows.length) for (const entry of retiring) remove(entry);
    // Hidden browser sources can suspend animations while SSE continues arriving.
    while (retiring.size > Math.max(4, rows.length * 2)) remove(retiring.values().next().value);
  }
  return { render };
}
module.exports = { createCaptionView };
