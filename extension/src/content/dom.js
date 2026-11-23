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
    // composed: inputs inside web components (shadow DOM) must reach the component's own listeners outside it too.
    el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  }

  // ---- shadow DOM (web-component forms such as SmartRecruiters) ---------------------------------------
  // Read-only traversal: open shadow roots, and closed ones through Chrome's own extension API when it exists.
  // Bounded (depth and node count) so a huge page can't stall the content script.
  const MAX_DEPTH = 12;
  const MAX_NODES = 20000;

  function shadowOf(el) {
    if (el.shadowRoot) return el.shadowRoot;
    try { return globalThis.chrome?.dom?.openOrClosedShadowRoot?.(el) || null; } catch { return null; }
  }

  /** Every element matching `selector` in `root` and in the shadow roots below it, in document order. */
  function deepAll(root, selector) {
    const out = [];
    let seen = 0;
    const walk = (node, depth) => {
      for (const el of node.querySelectorAll("*")) {
        if (++seen > MAX_NODES) return;
        if (el.matches(selector)) out.push(el);
        const sr = depth < MAX_DEPTH ? shadowOf(el) : null;
        if (sr) walk(sr, depth + 1);
      }
    };
    walk(root, 0);
    return out;
  }

  /** Counts that explain what a page holds when no form is recognised (diagnostics, no values). */
  function census(root = document.body) {
    let shadowHosts = 0; let closedHosts = 0; let deepFields = 0; let opaqueHosts = 0;
    const light = root.querySelectorAll("input:not([type=hidden]),select,textarea").length;
    const walk = (node, depth) => {
      for (const el of node.querySelectorAll("*")) {
        const sr = shadowOf(el);
        if (sr) {
          shadowHosts++;
          if (!el.shadowRoot) closedHosts++;
          deepFields += sr.querySelectorAll("input:not([type=hidden]),select,textarea").length;
          if (depth < MAX_DEPTH) walk(sr, depth + 1);
        } else if (el.localName.includes("-") && !el.children.length && visible(el)) {
          opaqueHosts++;  // a web component whose content can't be read (closed shadow root)
        }
      }
    };
    walk(root, 0);
    const frames = [...document.querySelectorAll("iframe")].map((f) => { try { return f.src ? new URL(f.src, location.href).hostname : "inline"; } catch { return "unknown"; } });
    return { forms: document.querySelectorAll("form").length, lightFields: light, shadowHosts, closedHosts, deepFields, opaqueHosts, frames: frames.slice(0, 6) };
  }

  /** Document order across shadow roots: -1 if `a` comes first. (compareDocumentPosition can't order nodes that
   *  live in different trees, so both are lifted to the first tree they share.) */
  function orderCompare(a, b) {
    const chain = (n) => { const out = []; while (n) { out.push(n); const r = n.getRootNode?.(); n = r && r.host ? r.host : null; } return out; };
    const ca = chain(a); const cb = chain(b);
    for (const x of ca) {
      const y = cb.find((n) => n.getRootNode?.() === x.getRootNode?.());
      if (!y) continue;
      if (x === y) return ca.indexOf(x) < cb.indexOf(y) ? 1 : -1;  // the one directly in this tree comes first
      return x.compareDocumentPosition(y) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    }
    return 0;
  }

  /** The element with this id in the same tree as `el` (its shadow root or the document). */
  function byId(el, id) {
    const r = el.getRootNode?.();
    return (r && typeof r.getElementById === "function" ? r.getElementById(id) : null) || el.ownerDocument.getElementById(id);
  }

  /** The nearest ancestor matching `selector`, crossing shadow-root boundaries (closest() stops at them). */
  function closestDeep(el, selector) {
    let n = el;
    while (n) {
      const hit = n.closest?.(selector);
      if (hit) return hit;
      const r = n.getRootNode?.();
      n = r && r.host ? r.host : null;
    }
    return null;
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
      const n = byId(el, id);
      if (n && visible(n) && /error|invalid|required|must|please/i.test(n.className + " " + n.textContent)) return textOf(n);
    }
    const box = closestDeep(el, "[class*='field'], [class*='question'], li, .form-group, fieldset");
    const err = box?.querySelector("[role=alert], [class*='error']:not(input):not(select):not(textarea), [class*='invalid']:not(input)");
    return err && visible(err) ? textOf(err) : "";
  }

  JP.dom = { clean, sleep, visible, choiceVisible, writable, textOf, setNativeValue, safeClick, waitFor, hash, errorTextFor,
             deepAll, census, byId, closestDeep, shadowOf, orderCompare };
})();
