// Fill engine shared by the platform adapters. Injected into allow-listed application frames only after a click.
//
// Rules enforced here (and tested):
//  * only visible, enabled, writable fields inside the application form are touched;
//  * a field that already has a value is kept unless the user chose "overwrite" (and a value the user typed after
//    JobPilot filled it is never replaced);
//  * each field is filled at most once per value, and each profile value goes into one field only;
//  * sensitive (demographic/EEO), consent, password/OTP/CAPTCHA and file fields are never filled by Fill;
//  * uncertain fields are skipped with a reason; nothing is ever submitted: no submit buttons are clicked, no form
//    submit()/requestSubmit() is called, and the only elements clicked are radio/checkbox inputs, listbox options and
//    type="button" choice buttons inside a question.
// No network, no storage, no cookies. Values never go to console logs.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.core) return;
  const { norm, profileKeyFor, classify, matchOption } = JP.fieldmap;

  const state = (JP.state ??= { filled: new WeakMap(), refs: new Map(), nextRef: 1, observer: null });
  const TEXT_TYPES = new Set(["text", "email", "tel", "url", "number", "search", ""]);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => String(s ?? "").replace(/\s+/g, " ").trim();

  // ---- reading the page ---------------------------------------------------------------------

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

  function labelFor(el, adapter) {
    const own = adapter.label?.(el);
    if (own) return clean(own);
    if (el.labels && el.labels.length) {
      const t = textOf(el.labels[0]);
      if (t) return t;
    }
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(/\s+/).map((id) => textOf(el.ownerDocument.getElementById(id))).filter(Boolean).join(" ");
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
      if (by) return clean(by.split(/\s+/).map((id) => textOf(first.ownerDocument.getElementById(id))).join(" "));
      if (role.getAttribute("aria-label")) return clean(role.getAttribute("aria-label"));
    }
    return "";
  }

  function choiceText(el) {
    return textOf(el.labels?.[0]) || textOf(el.closest("label")) || clean(el.value);
  }

  /**
   * The fillable questions of the application form, each:
   * {ref, kind: text|select|radio|checkbox|combobox|buttons|file, label, required, els, options?}
   */
  function scan(adapter) {
    const root = adapter.root() || document.body;
    const out = [];
    const groups = new Map();
    for (const el of root.querySelectorAll("input,textarea,select")) {
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
        out.push({ kind: "file", els: [el], label: labelFor(el, adapter), required: el.required });
        continue;
      }
      if (!visible(el) || !writable(el)) continue;
      if (tag === "select") {
        out.push({ kind: "select", els: [el], label: labelFor(el, adapter), required: el.required,
                   options: [...el.options].filter((o) => o.value !== "" && !o.disabled).map((o) => clean(o.text)) });
      } else if (el.getAttribute("role") === "combobox") {
        out.push({ kind: "combobox", els: [el], label: labelFor(el, adapter), required: el.getAttribute("aria-required") === "true" || el.required,
                   adapterValue: adapter.comboValue ? () => adapter.comboValue(el) : undefined });
      } else if (tag === "textarea" || TEXT_TYPES.has(type)) {
        out.push({ kind: "text", els: [el], label: labelFor(el, adapter), required: el.required || el.getAttribute("aria-required") === "true" });
      }
    }
    for (const g of groups.values()) {
      const label = groupLabel(g.els[0], adapter) || (g.els.length === 1 ? choiceText(g.els[0]) : "");
      out.push({ kind: g.type, els: g.els, label, required: g.els.some((e) => e.required), options: g.els.map(choiceText),
                 single: g.els.length === 1 });
    }
    for (const q of adapter.extraQuestions?.(root) ?? []) out.push(q);
    // Stable document order, and a ref per question for the review panel.
    out.sort((a, b) => (a.els[0].compareDocumentPosition(b.els[0]) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    for (const q of out) {
      q.ref = refFor(q.els[0]);
      q.label = clean(q.label).replace(/\s*[*✱]+\s*$/, "").trim();  // drop the "required" marker
    }
    return out;
  }

  function refFor(el) {
    for (const [ref, e] of state.refs) if (e === el) return ref;
    const ref = `f${state.nextRef++}`;
    state.refs.set(ref, el);
    return ref;
  }

  function currentValue(q) {
    if (q.kind === "radio" || q.kind === "checkbox") return q.els.filter((e) => e.checked).map(choiceText).join(", ");
    if (q.kind === "buttons") return q.els.filter((e) => e.getAttribute("aria-pressed") === "true" || /selected|active/.test(e.className)).map((e) => clean(e.textContent)).join(", ");
    if (q.kind === "combobox") return clean(q.adapterValue?.() ?? q.els[0].value);
    if (q.kind === "select") { const el = q.els[0]; return el.value ? clean(el.options[el.selectedIndex]?.text) : ""; }
    return clean(q.els[0].value);
  }

  // ---- writing values -----------------------------------------------------------------------

  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function safeClick(el) {
    // The only elements Fill ever clicks. Anything that could submit the form is refused.
    // (A <button> without an explicit type="button" is a submit button.)
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    const choiceInput = tag === "input" && (type === "radio" || type === "checkbox");
    const option = el.getAttribute("role") === "option" && !["button", "input", "a"].includes(tag);
    const choiceButton = tag === "button" && type === "button";
    if (!(choiceInput || option || choiceButton)) throw new Error("refused to click a non-choice element");
    el.click();
  }

  async function setText(q, value) {
    const el = q.els[0];
    el.focus({ preventScroll: true });
    setNativeValue(el, value);
    el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    el.blur();
    if (clean(el.value) === clean(value)) return true;
    // Phone widgets reformat numbers ("+91 90000 00000"): the same digits count as accepted.
    const digits = (v) => String(v).replace(/\D/g, "");
    return /^[\d\s()+.-]+$/.test(value) && digits(value).length >= 6 && digits(el.value) === digits(value);
  }

  function setChoice(q, index) {
    const el = q.els[index];
    if (q.kind === "radio" || q.kind === "checkbox") {
      if (!el.checked) safeClick(el);
      return el.checked;
    }
    if (q.kind === "buttons") { safeClick(el); return true; }
    if (q.kind === "select") {
      const sel = q.els[0];
      const opt = [...sel.options].filter((o) => o.value !== "" && !o.disabled)[index];
      setNativeValue(sel, opt.value);
      return sel.value === opt.value;
    }
    return false;
  }

  // ---- deciding what to write ---------------------------------------------------------------

  const NEVER = {
    sensitive: "Sensitive personal question (for example gender, ethnicity, veteran or disability status). JobPilot never answers these for you.",
    consent: "Consent or declaration. Only you can agree to this.",
    secret: "Password, code or CAPTCHA field. JobPilot never fills these.",
  };

  function degreeLike(value) {
    // Only used for option lists: map common degree abbreviations to the usual option wording (a suggestion).
    const v = norm(value).replace(/\./g, "");
    if (/^(mba|pgdm)\b/.test(v)) return ["Master of Business Administration (M.B.A.)", "MBA", "Master's Degree"];
    if (/^(b ?com|ba|bsc|b ?tech|be|bba|bca|bachelor)/.test(v)) return ["Bachelor's Degree", "Bachelor's", "Bachelors"];
    if (/^(m ?com|ma|msc|m ?tech|me|mca|master)/.test(v)) return ["Master's Degree", "Master's", "Masters"];
    return [];
  }

  /**
   * Fill the form. payload = {fields, facts, answers: {label: {answer, status}}, overwrite}
   * Returns a report: {filled, review, kept, skipped, needs, files}.
   */
  async function fill(adapter, payload) {
    const questions = scan(adapter);
    const report = { platform: adapter.name, filled: [], review: [], kept: [], skipped: [], needs: [], files: [] };
    const used = new Set();
    const answers = payload.answers || {};
    const fields = payload.fields || {};

    for (const q of questions) {
      const label = q.label || "(unlabelled field)";
      const item = { ref: q.ref, label };
      if (q.kind === "file") { report.files.push({ ...item, accept: q.els[0].accept || "" }); continue; }
      const never = classify(label) || JP.fieldmap.classifyOptions(q.options);
      if (never) { report.skipped.push({ ...item, reason: NEVER[never] }); continue; }
      const skip = adapter.skip?.(q);
      if (skip) { report.skipped.push({ ...item, reason: skip }); continue; }
      if (q.single && q.kind === "checkbox") { report.needs.push({ ...item, reason: "Tick this yourself if it applies." }); continue; }
      if (!q.label) { report.skipped.push({ ...item, reason: "No label, so JobPilot cannot tell what it asks." }); continue; }

      // What value does this field want?
      let value = null; let status = "VERIFIED"; let source = "profile";
      const key = adapter.profileKey?.(q) ?? profileKeyFor(label);
      if (key) {
        if (used.has(key) && !["first_name", "last_name"].includes(key)) { report.skipped.push({ ...item, reason: "Already filled in another field on this form." }); continue; }
        value = fields[key] ?? null;
        if (value == null || value === "") {
          report.needs.push({ ...item, reason: `Add your ${label.toLowerCase()} to your JobPilot profile.`, where: "settings/profile" });
          continue;
        }
        value = String(value);
      } else {
        const a = answers[label];
        if (!a || a.status === "NEEDS_INPUT" || a.answer == null) {
          report.needs.push({ ...item, reason: a?.reason ? `Needs your answer (${a.reason}).` : "Needs your answer." , where: "settings/answers" });
          continue;
        }
        value = String(a.answer); status = a.status; source = "answers";
      }

      // Respect what is already there.
      const current = currentValue(q);
      const ours = state.filled.get(q.els[0]);
      if (current) {
        if (ours != null && clean(ours) === clean(current)) { if (key) used.add(key); report.skipped.push({ ...item, reason: "Already filled by JobPilot." }); continue; }
        if (ours != null) { report.kept.push({ ...item, current, proposed: value, reason: "You changed this after JobPilot filled it." }); continue; }
        if (!payload.overwrite) {
          report.kept.push({ ...item, current, proposed: value, reason: "Already had a value. Kept it.", replaceable: q.kind === "text" });
          state.pending ??= new Map(); state.pending.set(q.ref, { q, value });
          if (key) used.add(key);
          continue;
        }
      }

      let ok = false; let shown = value;
      try {
        if (q.kind === "text") {
          ok = await setText(q, value);
        } else if (q.kind === "combobox") {
          const candidates = key === "degree" ? [value, ...degreeLike(value)] : [value];
          const res = await (adapter.chooseOption ?? JP.chooseComboOption)(q.els[0], candidates, { typeahead: key === "location" || key === "school" });
          ok = res.ok; if (res.text) shown = res.text;
          if (!ok) { report.skipped.push({ ...item, reason: res.reason || "No option matches your answer exactly. Choose it yourself." }); continue; }
          if (key === "degree" && norm(shown) !== norm(value)) status = "SUGGESTED";
        } else {
          let idx = matchOption(value, q.options || []);
          if (idx < 0 && key === "degree") for (const c of degreeLike(value)) { idx = matchOption(c, q.options || []); if (idx >= 0) { status = "SUGGESTED"; break; } }
          if (idx < 0) { report.skipped.push({ ...item, reason: `None of the options matches your answer "${value.slice(0, 60)}". Choose it yourself.` }); continue; }
          if (q.kind === "checkbox" && !q.single && answers[label] && status !== "VERIFIED") {
            report.needs.push({ ...item, reason: "Multiple-choice: please choose yourself." }); continue;
          }
          ok = setChoice(q, idx); shown = q.options[idx];
        }
      } catch (e) {
        report.skipped.push({ ...item, reason: "Could not be filled safely on this page." });
        continue;
      }
      if (!ok) { report.skipped.push({ ...item, reason: "The page did not accept the value. Fill it yourself." }); continue; }
      state.filled.set(q.els[0], currentValue(q) || shown);
      if (key) used.add(key);
      (status === "VERIFIED" ? report.filled : report.review).push({ ...item, value: shown, source,
        note: status === "SUGGESTED" ? "Suggested from your profile. Please check it." : undefined });
    }
    watchForNewFields(adapter);
    return report;
  }

  /** Replace one kept value with the JobPilot value, after the user clicked "Use JobPilot value" in the panel. */
  async function useProposed(ref) {
    const p = state.pending?.get(ref);
    if (!p || p.q.kind !== "text") return false;
    const ok = await setText(p.q, p.value);
    if (ok) { state.filled.set(p.q.els[0], clean(p.value)); state.pending.delete(ref); }
    return ok;
  }

  function watchForNewFields(adapter) {
    state.observer?.disconnect();
    const root = adapter.root() || document.body;
    const before = new Set(scan(adapter).map((q) => q.els[0]));
    let timer = null;
    state.observer = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const fresh = scan(adapter).filter((q) => q.kind !== "file" && !before.has(q.els[0]));
        if (fresh.length) JP.panel?.notice(`${fresh.length} new question${fresh.length > 1 ? "s" : ""} appeared. Open JobPilot and click Fill again to fill ${fresh.length > 1 ? "them" : "it"}.`);
      }, 600);
    });
    state.observer.observe(root, { childList: true, subtree: true });
    setTimeout(() => state.observer?.disconnect(), 5 * 60 * 1000);
  }

  // ---- generic combobox (ARIA listbox) ------------------------------------------------------

  async function waitFor(fn, ms = 3000, step = 100) {
    for (let t = 0; t < ms; t += step) { const v = fn(); if (v) return v; await sleep(step); }
    return fn();
  }

  function listboxOptions(input) {
    const id = input.getAttribute("aria-controls") || input.getAttribute("aria-owns");
    const box = (id && input.ownerDocument.getElementById(id)) || null;
    const scope = box || input.ownerDocument;
    return [...scope.querySelectorAll("[role=option]")].filter((o) => visible(o) && o.getAttribute("aria-disabled") !== "true");
  }

  function pickIndex(texts, candidates, { prefix }) {
    const n = texts.map(norm);
    for (const c of candidates) {
      const target = norm(c);
      if (!target) continue;
      const exact = n.flatMap((t, i) => (t === target ? [i] : []));
      if (exact.length === 1) return exact[0];
      if (prefix) {
        const pre = n.flatMap((t, i) => (t.startsWith(target + " ") ? [i] : []));
        if (pre.length === 1) return pre[0];
      }
      const m = matchOption(c, texts);
      if (m >= 0) return m;
    }
    return -1;
  }

  async function chooseComboOption(input, candidates, { typeahead = false } = {}) {
    const doc = input.ownerDocument;
    input.focus({ preventScroll: true });
    input.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", code: "ArrowDown", keyCode: 40, bubbles: true }));
    const queries = typeahead ? [candidates[0], String(candidates[0]).split(",")[0]] : [""];
    for (const [i, query] of [...new Set(queries)].entries()) {
      if (query) setNativeValue(input, query);
      const options = await waitFor(() => { const o = listboxOptions(input); return o.length ? o : null; }, typeahead ? (i === 0 ? 4000 : 2500) : 2000);
      if (!options) continue;
      const idx = pickIndex(options.map((o) => clean(o.textContent)), candidates, { prefix: typeahead });
      if (idx >= 0) {
        const opt = options[idx];
        const text = clean(opt.textContent);
        opt.scrollIntoView?.({ block: "nearest" });
        opt.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
        safeClick(opt);
        await sleep(150);
        return { ok: true, text };
      }
    }
    // Leave the field as we found it.
    if (input.value) setNativeValue(input, "");
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
    input.blur();
    doc.activeElement?.blur?.();
    return { ok: false, reason: typeahead ? "No suggestion matched your profile exactly. Type and choose it yourself." : "No option matches your answer exactly. Choose it yourself." };
  }

  // ---- resume ------------------------------------------------------------------------------

  function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  /** Attach the resume to the platform's resume input (explicit "Attach resume" click in the popup). */
  async function attachResume(adapter, file, { replace = false } = {}) {
    const input = adapter.resumeInput?.();
    if (!input) return { ok: false, reason: "No resume upload field was found on this page. Use Download resume and attach it yourself." };
    if (input.disabled) return { ok: false, reason: "The resume field is disabled." };
    if (input.files && input.files.length && !replace && !adapter.hasResume?.()) {
      return { ok: false, needsConfirm: true, reason: "A file is already attached. Click Replace to use your JobPilot resume instead." };
    }
    if (adapter.hasResume?.() && !replace) return { ok: false, needsConfirm: true, reason: "A resume is already attached. Click Replace to use your JobPilot resume instead." };
    const accept = (input.accept || "").toLowerCase();
    if (accept && !accept.includes("pdf") && !accept.includes("application/pdf") && !accept.includes("*")) {
      return { ok: false, reason: "This form does not accept PDF files. Attach a suitable file yourself." };
    }
    try {
      const f = new File([b64ToBytes(file.b64)], file.name, { type: file.type || "application/pdf", lastModified: Date.now() });
      const dt = new DataTransfer();
      dt.items.add(f);
      input.files = dt.files;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    } catch {
      return { ok: false, reason: "This browser did not allow attaching the file automatically. Use Download resume and attach it yourself." };
    }
    const accepted = await waitFor(() => (adapter.hasResume ? adapter.hasResume() : input.files?.length > 0), 4000);
    return accepted ? { ok: true, name: file.name, note: adapter.afterResumeNote }
                    : { ok: false, reason: "The page did not accept the file. Use Download resume and attach it yourself." };
  }

  // ---- entry points (called by the service worker through chrome.scripting) -----------------

  function adapterHere() {
    const host = location.hostname;
    return Object.values(JP.adapters).find((a) => a.hosts.includes(host) && a.isApplicationPage()) || null;
  }

  JP.core = { scan, fill, visible, labelFor, textOf, setNativeValue, safeClick, matchOption, currentValue, waitFor };
  JP.chooseComboOption = chooseComboOption;

  JP.detect = () => {
    const a = adapterHere();
    if (!a) return { url: location.href, platform: null };
    const qs = scan(a);
    return {
      url: location.href, platform: a.name, title: a.jobTitle?.() || null,
      fields: qs.filter((q) => q.kind !== "file").length,
      questions: qs.filter((q) => q.kind !== "file" && q.label && !(a.profileKey?.(q) ?? profileKeyFor(q.label)) && !classify(q.label)).map((q) => q.label),
      resumeField: Boolean(a.resumeInput?.()), resumeAttached: Boolean(a.hasResume?.()),
      resumeFirst: Boolean(a.resumeFirst),
    };
  };

  JP.fill = async (payload) => {
    const a = adapterHere();
    if (!a) return { error: "This page is not a supported application form." };
    const report = await fill(a, payload);
    JP.panel?.show(report);
    return report;
  };

  JP.attachResume = async (file, opts) => {
    const a = adapterHere();
    if (!a) return { ok: false, reason: "This page is not a supported application form." };
    const res = await attachResume(a, file, opts);
    file.b64 = null;  // drop the bytes from this script's memory
    return res;
  };

  JP.useProposed = useProposed;
})();
