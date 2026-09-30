"use strict";

// Minimal DOM for renderer tests: element trees with textContent, dataset, classList,
// events and scroll geometry. Not a browser; only what the default renderer uses.
class FakeNode {
  constructor(tagName = "div", text = null) {
    this.tagName = tagName;
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.style = {};
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.className = "";
    this.title = "";
    this.listeners = new Map();
    this._text = text;
    this.scrollTop = 0;
    this.clientHeight = 100;
    this.lineHeight = 20;
    const classes = new Set();
    this.classList = {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      toggle: (c, on) => ((on === undefined ? !classes.has(c) : on) ? classes.add(c) : classes.delete(c)),
      contains: (c) => classes.has(c),
    };
  }

  get textContent() {
    if (this._text !== null) return this._text;
    return this.children.map((c) => c.textContent).join("");
  }

  set textContent(value) {
    this.children = [];
    this._text = this.tagName === "#text" ? String(value) : null;
    if (this.tagName !== "#text" && value !== "") {
      const node = new FakeNode("#text", String(value));
      node.parentNode = this;
      this.children.push(node);
    }
  }

  // Treat each child element as one line, so appending grows the scroll height.
  get scrollHeight() {
    const lines = this.children.filter((c) => c.tagName !== "#text").length || 1;
    return Math.max(this.clientHeight, lines * this.lineHeight);
  }

  appendChild(node) {
    node.parentNode = this;
    this.children.push(node);
    return node;
  }

  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }

  dispatch(type, props = {}) {
    let prevented = false;
    const event = { type, target: this, preventDefault: () => { prevented = true; }, ...props };
    for (const fn of this.listeners.get(type) || []) fn(event);
    return prevented;
  }
}

function createFakeDocument() {
  const byId = new Map();
  return {
    byId,
    getElementById(id) {
      if (!byId.has(id)) byId.set(id, new FakeNode("div"));
      return byId.get(id);
    },
    createElement: (tag) => new FakeNode(tag),
    createTextNode: (text) => new FakeNode("#text", String(text)),
    addEventListener() {},
  };
}

module.exports = { FakeNode, createFakeDocument };
