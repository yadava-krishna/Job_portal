// Fill engine shared by the platform adapters. Injected into allow-listed application frames only after a click.
//
// Rules enforced here (and tested):
//  * only visible, enabled, writable fields inside the application form are touched;
//  * a field is filled only when the classifier is confident (FILL_THRESHOLD) or the site adapter maps it exactly;
//    uncertain fields are listed as "not sure" and filled only if the user clicks "Use JobPilot value";
//  * a field that already has a value is kept unless the user chose "overwrite" (and a value the user typed after
//    JobPilot filled it is never replaced);
//  * each field is filled at most once per value, and each profile value goes into one field only;
//  * sensitive (demographic/EEO), consent, password/OTP/CAPTCHA and file fields are never filled by Fill;
//  * answers about salary, notice, work authorisation, sponsorship and relocation come only from what the user
//    confirmed, and are flagged so the user ticks each one before an assisted submission;
//  * nothing is ever submitted: no submit buttons are clicked, no form submit()/requestSubmit() is called, and the
//    only elements clicked are radio/checkbox inputs, listbox options and type="button" choice buttons.
//  * answers the server marks sensitivity "never" are never filled ("Answer this yourself"); stale answers are only
//    suggestions for review, never silently verified;
//  * a date picker (<input type=date>) is filled only with an ISO date (YYYY-MM-DD), otherwise left to the user;
//  * the prepared cover letter goes only into a text box labelled "cover letter", as a suggestion to review (cover
//    letter file uploads are never touched).
// Every value JobPilot writes is remembered with its source, so the review shows where each answer came from.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.filler) return;
  const { clean, sleep, visible, setNativeValue, safeClick, waitFor } = JP.dom;
  const { norm, classify, classifyOptions, classifyField, matchOption, FILL_THRESHOLD } = JP.fieldmap;
  const { scan, currentValue, state } = JP.scan;

  const NEVER = {
    sensitive: "Sensitive personal question (for example gender, ethnicity, veteran or disability status). JobPilot never answers these for you.",
    consent: "Consent or declaration. Only you can agree to this.",
    secret: "Password, code or CAPTCHA field. JobPilot never fills these.",
  };
  const KEY_WORDS = {
    first_name: "first name", last_name: "last name", full_name: "full name", phone_country_code: "phone country code",
    phone_national: "phone number", address_line1: "address", postal_code: "postal code", graduation_year: "graduation year",
    current_company: "current company", current_title: "current job title", linkedin_url: "LinkedIn URL", github_url: "GitHub URL",
    portfolio_url: "portfolio URL", website_url: "website",
  };
  // Answers that commit the candidate to something: always flagged for an explicit tick before assisted submission.
  const CONFIRM_SOURCES = /^verified_facts\.(current_ctc|expected_ctc|notice_period|work_authorization|requires_sponsorship|willing_to_relocate|earliest_start_date)/;
  const CONFIRM_LABEL = /\b(salary|ctc|compensation|notice period|authori[sz]|sponsor|visa|relocat|start date|joining)\b/;
  const COVER_LETTER = /^(your )?cover (letter|note)\b|\bcover letter$/;
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

  /** Which profile value a question wants: {key, confidence, via, never?}. Shared by detect() and fill(). */
  function keyFor(adapter, q) {
    const mapped = adapter.profileKey?.(q);
    if (mapped) return { key: mapped, confidence: 0.99, via: ["site"] };
    if (q.kind === "file" || q.kind === "buttons") return { key: null, confidence: 0, via: [] };
    const c = classifyField(q.signals || { label: q.label });
    if (c?.never) return c;
    const optionsNever = classifyOptions(q.options);
    if (optionsNever) return { never: optionsNever, key: null, confidence: 1, via: ["options"] };
    return c || { key: null, confidence: 0, via: [] };
  }

  function degreeLike(value) {
    // Only used for option lists: map common degree abbreviations to the usual option wording (a suggestion).
    const v = norm(value).replace(/\./g, "");
    if (/^(mba|pgdm)\b/.test(v)) return ["Master of Business Administration (M.B.A.)", "MBA", "Master's Degree"];
    if (/^(b ?com|ba|bsc|b ?tech|be|bba|bca|bachelor)/.test(v)) return ["Bachelor's Degree", "Bachelor's", "Bachelors"];
    if (/^(m ?com|ma|msc|m ?tech|me|mca|master)/.test(v)) return ["Master's Degree", "Master's", "Masters"];
    return [];
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

  // ---- custom dropdowns ---------------------------------------------------------------------

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

  async function chooseListButton(btn, candidates) {
    safeClick(btn);
    const options = await waitFor(() => { const o = listboxOptions(btn); return o.length ? o : null; }, 2500);
    if (options) {
      const idx = pickIndex(options.map((o) => clean(o.textContent)), candidates, { prefix: false });
      if (idx >= 0) {
        const text = clean(options[idx].textContent);
        safeClick(options[idx]);
        await sleep(150);
        return { ok: true, text };
      }
    }
    btn.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
    return { ok: false, reason: "No option matches your answer exactly. Choose it yourself." };
  }

  // ---- filling ------------------------------------------------------------------------------

  /**
   * Fill the form. payload = {fields, answers: {label: {answer, status, source, confirm, stale, sensitivity, ...}}, coverLetter?, overwrite}
   * Returns a report: {filled, review, unsure, kept, skipped, needs, files}.
   */
  async function fill(adapter, payload) {
    const questions = scan(adapter);
    const report = { platform: adapter.name, filled: [], review: [], unsure: [], kept: [], skipped: [], needs: [], files: [] };
    const used = new Set();
    const answers = payload.answers || {};
    const fields = payload.fields || {};
    const derived = new Set(fields._derived || []);
    state.pending ??= new Map();
    state.answers = answers;  // what JobPilot proposed for each question (the review panel's "save for next time" reads it)

    for (const q of questions) {
      const label = q.label || "(unlabelled field)";
      const item = { ref: q.ref, label };
      if (q.kind === "file") { report.files.push({ ...item, accept: q.els[0].accept || "" }); continue; }
      const cls = keyFor(adapter, q);
      if (cls.never) { report.skipped.push({ ...item, reason: NEVER[cls.never] }); continue; }
      const skip = adapter.skip?.(q);
      if (skip) { report.skipped.push({ ...item, reason: skip }); continue; }
      if (q.single && q.kind === "checkbox") { report.needs.push({ ...item, reason: "Tick this yourself if it applies." }); continue; }
      if (!q.label && !(cls.key && cls.confidence >= FILL_THRESHOLD)) { report.skipped.push({ ...item, reason: "No label, so JobPilot cannot tell what it asks." }); continue; }

      // What value does this field want, and how sure are we?
      let value = null; let status = "VERIFIED"; let source = "profile"; let confirm = false;
      const key = cls.key && cls.confidence >= 0.4 ? cls.key : null;
      if (key) {
        if (used.has(key) && !["first_name", "last_name"].includes(key)) { report.skipped.push({ ...item, reason: "Already filled in another field on this form." }); continue; }
        value = fields[key] ?? null;
        if (value == null || value === "") {
          if (cls.confidence < FILL_THRESHOLD) { report.needs.push({ ...item, reason: "Needs your answer." }); continue; }
          report.needs.push({ ...item, reason: `Add your ${KEY_WORDS[key] || label.toLowerCase()} to your JobPilot profile.`, where: "settings/profile" });
          continue;
        }
        value = String(value);
        if (derived.has(key)) status = "SUGGESTED";
        if (cls.confidence < FILL_THRESHOLD) {
          // Not sure enough to fill: offer it, never write it on our own.
          const why = cls.conflict ? "The field's label and its code disagree" : "JobPilot is not sure what this field asks";
          report.unsure.push({ ...item, proposed: value, reason: `${why}. It may want your ${KEY_WORDS[key] || key.replace(/_/g, " ")}.`, replaceable: q.kind === "text" });
          state.pending.set(q.ref, { q, value, key, source, status: "SUGGESTED" });
          continue;
        }
      } else {
        const a = answers[label];
        const cover = payload.coverLetter && q.kind === "text" && q.els[0].tagName === "TEXTAREA" && COVER_LETTER.test(norm(label));
        if (a?.sensitivity === "never") { report.needs.push({ ...item, reason: "Answer this yourself.", never: true }); continue; }
        if (cover && (!a || a.status === "NEEDS_INPUT" || a.answer == null)) {
          // The cover letter prepared for this application: a suggestion the user reviews, never "verified".
          value = String(payload.coverLetter); status = "SUGGESTED"; source = "cover letter";
        } else if (!a || a.status === "NEEDS_INPUT" || a.answer == null) {
          report.needs.push({ ...item, reason: a?.reason ? `Needs your answer (${a.reason}).` : "Needs your answer.", where: "settings/answers" });
          continue;
        } else {
          value = String(a.answer); status = a.stale ? "SUGGESTED" : a.status === "VERIFIED" ? "VERIFIED" : "SUGGESTED";
          source = String(a.source || "").startsWith("answer_bank") ? "saved answer" : "answers";
          confirm = CONFIRM_SOURCES.test(a.source || "") || CONFIRM_LABEL.test(norm(label)) || Boolean(a.confirm);
        }
      }
      if (q.kind === "date" && !ISO_DATE.test(value.trim())) { report.needs.push({ ...item, reason: "Pick the date yourself." }); continue; }

      // Respect what is already there.
      const current = currentValue(q);
      const ours = state.filled.get(q.els[0]);
      if (current) {
        if (ours != null && clean(ours.value) === clean(current)) { if (key) used.add(key); report.skipped.push({ ...item, reason: "Already filled by JobPilot." }); continue; }
        if (ours != null) { report.kept.push({ ...item, current, proposed: value, reason: "You changed this after JobPilot filled it." }); continue; }
        if (!payload.overwrite) {
          report.kept.push({ ...item, current, proposed: value, reason: "Already had a value. Kept it.", replaceable: q.kind === "text" });
          state.pending.set(q.ref, { q, value, key, source, status, confirm });
          if (key) used.add(key);
          continue;
        }
      }

      let ok = false; let shown = value;
      try {
        if (q.kind === "text") {
          ok = await setText(q, value);
        } else if (q.kind === "date") {
          ok = await setText(q, value.trim());
        } else if (q.kind === "combobox" || q.kind === "listbutton") {
          const candidates = key === "degree" ? [value, ...degreeLike(value)] : [value];
          const res = q.kind === "combobox"
            ? await (adapter.chooseOption ?? chooseComboOption)(q.els[0], candidates, { typeahead: key === "location" || key === "school" || key === "city" })
            : await chooseListButton(q.els[0], candidates);
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
      } catch {
        report.skipped.push({ ...item, reason: "Could not be filled safely on this page." });
        continue;
      }
      if (!ok) { report.skipped.push({ ...item, reason: "The page did not accept the value. Fill it yourself." }); continue; }
      state.filled.set(q.els[0], { value: currentValue(q) || shown, source, status, key, confirm });
      if (key) used.add(key);
      (status === "VERIFIED" ? report.filled : report.review).push({ ...item, value: shown, source, confirm: confirm || undefined,
        note: status !== "SUGGESTED" ? undefined : source === "cover letter" ? "Your prepared cover letter. Please read and adjust it."
          : source === "profile" ? "Suggested from your profile. Please check it." : "Suggested from your saved answers. Please check it's still right." });
    }
    watchForNewFields(adapter);
    return report;
  }

  /** Write one proposed value (kept or not-sure field), after the user clicked "Use JobPilot value" in the panel. */
  async function useProposed(ref) {
    const p = state.pending?.get(ref);
    if (!p || p.q.kind !== "text") return false;
    const ok = await setText(p.q, p.value);
    if (ok) {
      state.filled.set(p.q.els[0], { value: clean(p.value), source: p.source || "profile", status: "VERIFIED", key: p.key, confirm: p.confirm, byUser: true });
      state.pending.delete(ref);
    }
    return ok;
  }

  function watchForNewFields(adapter) {
    state.observer?.disconnect();
    const root = adapter.root() || document.body;
    const before = new Set(scan(adapter).map((q) => q.els[0]));
    const stepBefore = adapter.step?.()?.title || null;
    let timer = null;
    state.observer = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const step = adapter.step?.()?.title || null;
        if (step && step !== stepBefore) { JP.panel?.stepChanged?.(adapter.step()); return; }
        const fresh = scan(adapter).filter((q) => q.kind !== "file" && !before.has(q.els[0]));
        if (fresh.length) JP.panel?.notice(`${fresh.length} new question${fresh.length > 1 ? "s" : ""} appeared. Click Fill again to fill ${fresh.length > 1 ? "them" : "it"}.`);
      }, 600);
    });
    state.observer.observe(root, { childList: true, subtree: true });
    setTimeout(() => state.observer?.disconnect(), 10 * 60 * 1000);
  }

  JP.filler = { fill, useProposed, keyFor, chooseComboOption, setText };
  JP.chooseComboOption = chooseComboOption;
})();
