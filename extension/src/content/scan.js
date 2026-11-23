// Page analysis: the questions of the application form, each with every signal the classifier needs.
// Read-only: nothing here changes the page.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.scan) return;
  const { clean, visible, choiceVisible, writable, textOf, byId, deepAll } = JP.dom;
  // Adapters for web-component forms (adapter.deep) are scanned through shadow roots too.
  const all = (adapter, root, selector) => (adapter.deep ? deepAll(root, selector) : [...root.querySelectorAll(selector)]);

  const state = (JP.state ??= { filled: new WeakMap(), refs: new Map(), nextRef: 1, observer: null });
  const TEXT_TYPES = new Set(["text", "email", "tel", "url", "number", "search", ""]);

  function labelFor(el, adapter) {
    const own = adapter.label?.(el);
    if (own) return clean(own);
    if (el.labels && el.labels.length) {
      const t = textOf(el.labels[0]);
      if (t) return t;
    }
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(/\s+/).map((id) => textOf(byId(el, id))).filter(Boolean).join(" ");
      if (t) return clean(t);
    }
    if (el.getAttribute("aria-label")) return clean(el.getAttribute("aria-label"));
    const legend = el.closest("fieldset")?.querySelector("legend");
    if (legend) return textOf(legend);
    return "";
  }

  function groupLabel(first, adapter) {
    const own = adapter.groupLabel?.(first);
    if (own) return clean(own);
    const fs = first.closest("fieldset");
    const legend = fs?.querySelector("legend");
    if (legend) return textOf(legend);
    const role = first.closest("[role=radiogroup],[role=group]");
    if (role) {
      const by = role.getAttribute("aria-labelledby");
      if (by) return clean(by.split(/\s+/).map((id) => textOf(byId(first, id))).join(" "));
      if (role.getAttribute("aria-label")) return clean(role.getAttribute("aria-label"));
    }
    return "";
  }

  function choiceText(el) {
    return textOf(el.labels?.[0]) || textOf(el.closest("label")) || clean(el.value);
  }

  function signals(el, label) {
    return { label, autocomplete: el.getAttribute("autocomplete") || "", name: el.getAttribute("name") || "", id: el.id || "",
             placeholder: el.getAttribute("placeholder") || "", type: (el.getAttribute("type") || "").toLowerCase() };
  }

  // Whether the form says a question must be answered. Only what the page itself says counts:
  //  * required: the required attribute, aria-required="true", or a "*" / "(required)" marker in its label;
  //  * optional: the label says "(optional)" (or "optional" on its own);
  //  * unknown: none of these. An unknown question is never treated as optional by JobPilot.
  const REQUIRED_MARK = /[*✱]\s*$|\(required\)|^\s*required\b|\brequired\s*$/i;
  const OPTIONAL_MARK = /\(optional\)|\boptional\s*$|^\s*optional\b/i;

  function requirementOf(attrRequired, rawLabel) {
    if (attrRequired) return "required";
    const t = String(rawLabel || "");
    if (OPTIONAL_MARK.test(t)) return "optional";
    if (REQUIRED_MARK.test(t)) return "required";
    return "unknown";
  }

  function refFor(el) {
    for (const [ref, e] of state.refs) if (e === el) return ref;
    const ref = `f${state.nextRef++}`;
    state.refs.set(ref, el);
    return ref;
  }

  /**
   * The fillable questions of the application form, each:
   * {ref, kind: text|date|select|radio|checkbox|combobox|listbutton|buttons|file, label, required, els, options?, signals}
   */
  function scan(adapter) {
    const root = adapter.root() || document.body;
    const out = [];
    const groups = new Map();
    for (const el of all(adapter, root, "input,textarea,select")) {
      if (adapter.ignore?.(el)) continue;
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (["hidden", "password", "submit", "button", "image", "reset"].includes(type)) continue;
      if (/captcha/i.test(el.name || "") || /captcha/i.test(el.id || "")) continue;
      if (type === "radio" || type === "checkbox") {
        if (!choiceVisible(el) || !writable(el)) continue;
        const key = `${type}:${el.name || el.id}`;
        if (!groups.has(key)) groups.set(key, { type, els: [] });
        groups.get(key).els.push(el);
        continue;
      }
      if (type === "file") {
        out.push({ kind: "file", els: [el], label: labelFor(el, adapter), required: el.required, signals: signals(el, "") });
        continue;
      }
      if (!visible(el) || !writable(el)) continue;
      const label = labelFor(el, adapter);
      const required = el.required || el.getAttribute("aria-required") === "true";
      if (tag === "select") {
        out.push({ kind: "select", els: [el], label, required, signals: signals(el, label),
                   options: [...el.options].filter((o) => o.value !== "" && !o.disabled).map((o) => clean(o.text)) });
      } else if (el.getAttribute("role") === "combobox") {
        out.push({ kind: "combobox", els: [el], label, required, signals: signals(el, label),
                   adapterValue: adapter.comboValue ? () => adapter.comboValue(el) : undefined });
      } else if (tag === "input" && type === "date") {
        // A native date picker takes only an ISO date (YYYY-MM-DD); anything else is left to the user.
        out.push({ kind: "date", els: [el], label, required, signals: signals(el, label) });
      } else if (tag === "textarea" || TEXT_TYPES.has(type)) {
        out.push({ kind: "text", els: [el], label, required, signals: signals(el, label) });
      }
    }
    for (const g of groups.values()) {
      const label = groupLabel(g.els[0], adapter) || (g.els.length === 1 ? choiceText(g.els[0]) : "");
      out.push({ kind: g.type, els: g.els, label, required: g.els.some((e) => e.required), options: g.els.map(choiceText),
                 single: g.els.length === 1, signals: signals(g.els[0], label) });
    }
    // Custom dropdowns that are a button opening a listbox (Workday and others).
    for (const btn of all(adapter, root, "button[aria-haspopup='listbox']")) {
      if (adapter.ignore?.(btn) || !visible(btn) || !writable(btn) || (btn.getAttribute("type") || "").toLowerCase() !== "button") continue;
      const label = labelFor(btn, adapter);
      out.push({ kind: "listbutton", els: [btn], label, required: btn.getAttribute("aria-required") === "true",
                 signals: signals(btn, label) });
    }
    for (const q of adapter.extraQuestions?.(root) ?? []) out.push({ signals: { label: q.label }, ...q });
    // Stable document order, and a ref per question for the review panel.
    out.sort((a, b) => JP.dom.orderCompare(a.els[0], b.els[0]));
    for (const q of out) {
      q.ref = refFor(q.els[0]);
      q.requirement = q.requirement || requirementOf(Boolean(q.required), clean(q.label));
      q.required = q.requirement === "required";
      q.label = clean(q.label).replace(/\s*[*✱]+\s*$/, "").replace(/\s*\((optional|required)\)\s*$/i, "").trim();  // drop the markers
      if (q.signals) q.signals.label = q.label;
    }
    return out;
  }

  function listbuttonValue(btn) {
    const t = clean(btn.textContent);
    return /^(select( one)?|choose|--|please select)/i.test(t) ? "" : t;
  }

  function currentValue(q) {
    if (q.kind === "radio" || q.kind === "checkbox") return q.els.filter((e) => e.checked).map(choiceText).join(", ");
    if (q.kind === "buttons") return q.els.filter((e) => e.getAttribute("aria-pressed") === "true" || /selected|active/.test(e.className)).map((e) => clean(e.textContent)).join(", ");
    if (q.kind === "combobox") return clean(q.adapterValue?.() ?? q.els[0].value);
    if (q.kind === "listbutton") return listbuttonValue(q.els[0]);
    if (q.kind === "file") return [...(q.els[0].files || [])].map((f) => f.name).join(", ");
    if (q.kind === "select") { const el = q.els[0]; return el.value ? clean(el.options[el.selectedIndex]?.text) : ""; }
    return clean(q.els[0].value);
  }

  JP.scan = { scan, labelFor, groupLabel, choiceText, currentValue, refFor, requirementOf, state };
})();
