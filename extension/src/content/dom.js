// DOM helpers shared by every Smart Apply content script. Injected into allow-listed application frames only after
// a click in the extension. No network, no storage, no cookies; values never go to console logs.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.dom) return;

  const clean = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function visible(el) {
    if (!el || !el.isConnected) return false;
    if (el.closest("[hidden],[aria-hidden='true'],[inert]")) return false;
    if (typeof el.checkVisibility === "function") {
      if (!el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true })) return false;
    } else {
      const s = getComputedStyle(el);
      if (s.display === "none" || s.visibility === "hidden") return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  /** Custom-styled radios/checkboxes hide the input itself: treat them as visible if their label is. */
  function choiceVisible(el) {
    return visible(el) || [...(el.labels || [])].some(visible) || visible(el.closest("label"));
  }

  function writable(el) {
    return !el.disabled && !el.readOnly && !el.closest("fieldset[disabled]") && el.getAttribute("aria-disabled") !== "true";
  }

  function textOf(node) {
    if (!node) return "";
    const c = node.cloneNode(true);
    c.querySelectorAll("input,select,textarea,button,script,style,[aria-hidden='true']").forEach((n) => n.remove());
    return clean(c.textContent);
  }

  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** The only clicks Fill ever makes. Anything that could submit, navigate or upload is refused. */
  function safeClick(el) {
    // (A <button> without an explicit type="button" is a submit button.)
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    const choiceInput = tag === "input" && (type === "radio" || type === "checkbox");
    const option = el.getAttribute("role") === "option" && !["button", "input", "a"].includes(tag);
    const choiceButton = tag === "button" && type === "button";
    if (!(choiceInput || option || choiceButton)) throw new Error("refused to click a non-choice element");
    el.click();
  }

  async function waitFor(fn, ms = 3000, step = 100) {
    for (let t = 0; t < ms; t += step) { const v = fn(); if (v) return v; await sleep(step); }
    return fn();
  }

  /** Small stable hash (FNV-1a, 32-bit) used to fingerprint the form's state. Not a security measure. */
  function hash(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h.toString(16).padStart(8, "0");
  }

  /** Text of the element's nearest visible error message (aria-describedby / aria-errormessage / common classes). */
  function errorTextFor(el) {
    const ids = [el.getAttribute("aria-errormessage"), ...(el.getAttribute("aria-describedby") || "").split(/\s+/)].filter(Boolean);
    for (const id of ids) {
      const n = el.ownerDocument.getElementById(id);
      if (n && visible(n) && /error|invalid|required|must|please/i.test(n.className + " " + n.textContent)) return textOf(n);
    }
    const box = el.closest("[class*='field'], [class*='question'], li, .form-group, fieldset");
    const err = box?.querySelector("[role=alert], [class*='error']:not(input):not(select):not(textarea), [class*='invalid']:not(input)");
    return err && visible(err) ? textOf(err) : "";
  }

  JP.dom = { clean, sleep, visible, choiceVisible, writable, textOf, setNativeValue, safeClick, waitFor, hash, errorTextFor };
})();
