// Review before submission. The preview is read from the form as it is now (not from what JobPilot meant to
// fill), and a fingerprint of that state is taken. Any later change to the form makes the review stale.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.review) return;
  const { clean, hash, errorTextFor } = JP.dom;
  const { scan, currentValue, state } = JP.scan;

  const PERSONAL = new Set(["full_name", "first_name", "last_name", "email", "phone", "phone_country_code", "phone_national", "location",
                            "city", "state", "country", "postal_code", "address_line1", "linkedin_url", "github_url", "portfolio_url", "website_url"]);
  const PROFESSIONAL = new Set(["current_company", "current_title", "school", "degree", "graduation_year", "university"]);

  function sourceOf(q) {
    const ours = state.filled.get(q.els[0]);
    const now = currentValue(q);
    if (!now) return { kind: "empty", text: "Empty" };
    if (ours && clean(ours.value) === clean(now)) {
      const from = ours.source === "saved answer" ? "your saved answer" : ours.source === "answers" ? "your confirmed answers" : "your JobPilot profile";
      return { kind: ours.status === "VERIFIED" ? "jobpilot" : "suggested", text: ours.status === "VERIFIED" ? `JobPilot, from ${from}` : `JobPilot suggestion (from ${from}): please check`,
               confirm: Boolean(ours.confirm) };
    }
    if (ours) return { kind: "user", text: "You changed this" };
    return { kind: "page", text: "Already on the form (not from JobPilot)" };
  }

  function invalid(q) {
    const el = q.els[0];
    const empty = !currentValue(q);
    if (q.required && empty) return "Required, and still empty.";
    if (el.getAttribute?.("aria-invalid") === "true") return errorTextFor(el) || "The site marks this answer as invalid.";
    if (el.validity && !el.validity.valid && !empty) return el.validationMessage || errorTextFor(el) || "The site does not accept this value.";
    return null;
  }

  /** Fingerprint of everything that matters: each question, its value, and attached file names. */
  function fingerprint(questions) {
    return hash(JSON.stringify(questions.map((q) => [q.ref, q.label, currentValue(q)])));
  }

  /**
   * The preview: {job, personal, professional, screening, documents, validation, fingerprint, step, counts}.
   * ctx = {job: {title, company, location, url}, keyFor} from the caller.
   */
  function snapshot(adapter, ctx = {}) {
    const questions = scan(adapter);
    const keyFor = JP.filler.keyFor;
    const groups = { personal: [], professional: [], screening: [] };
    const validation = { missing: [], invalid: [], unsupported: [], confirm: [], uploadErrors: [], warnings: [] };
    for (const q of questions) {
      if (q.kind === "file") continue;
      const cls = keyFor(adapter, q);
      const src = sourceOf(q);
      const problem = invalid(q);
      const item = { ref: q.ref, label: q.label || "(unlabelled field)", value: currentValue(q), required: Boolean(q.required), source: src.text,
                     sourceKind: src.kind, confirm: Boolean(src.confirm), confirmed: Boolean(state.confirmed?.has(q.ref)), problem,
                     manual: Boolean(cls.never) };
      if (cls.never) item.note = cls.never === "sensitive" ? "Personal question: answer it yourself (optional questions can be left blank)."
        : cls.never === "consent" ? "Only you can agree to this." : "Fill this yourself.";
      const group = cls.key && PERSONAL.has(cls.key) ? "personal" : cls.key && PROFESSIONAL.has(cls.key) ? "professional" : "screening";
      groups[group].push(item);
      if (problem && q.required && !item.value) validation.missing.push(item.label);
      else if (problem) validation.invalid.push(`${item.label}: ${problem}`);
      if (item.confirm && !item.confirmed && item.value) validation.confirm.push(item.label);
      if (src.kind === "suggested") validation.warnings.push(`${item.label}: JobPilot suggestion, check it.`);
    }
    const documents = JP.resume.attachments(adapter, questions);
    for (const d of documents) {
      if (d.error) validation.uploadErrors.push(`${d.label}: ${d.error}`);
      else if (d.required && !d.attached) validation.missing.push(d.label);
    }
    for (const w of adapter.warnings?.() ?? []) validation.warnings.push(w);
    const counts = { fields: questions.filter((q) => q.kind !== "file").length,
                     filled: questions.filter((q) => q.kind !== "file" && currentValue(q)).length };
    return {
      job: { title: ctx.job?.title || adapter.jobTitle?.() || null, company: ctx.job?.company || adapter.company?.() || null,
             location: ctx.job?.location || null, url: location.href.split("?")[0] },
      ...groups, documents, validation, counts, step: adapter.step?.() || null, platform: adapter.name,
      fingerprint: fingerprint(questions),
      ready: !validation.missing.length && !validation.invalid.length && !validation.uploadErrors.length,
    };
  }

  /** The user ticked "I checked this answer" for a sensitive item. Stored only in this page's memory. */
  function setConfirmed(ref, yes) {
    state.confirmed ??= new Set();
    if (yes) state.confirmed.add(ref); else state.confirmed.delete(ref);
  }

  /** Call onStale() whenever the form changes after a review was taken (debounced). Returns a stop function. */
  function watch(adapter, reviewedFingerprint, onStale) {
    const root = adapter.root() || document.body;
    let timer = null;
    const check = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const now = fingerprint(scan(adapter));
        if (now !== reviewedFingerprint) onStale(now);
      }, 250);
    };
    root.addEventListener("input", check, true);
    root.addEventListener("change", check, true);
    const mo = new MutationObserver(check);
    mo.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-invalid", "aria-pressed", "class"] });
    return () => { root.removeEventListener("input", check, true); root.removeEventListener("change", check, true); mo.disconnect(); clearTimeout(timer); };
  }

  JP.review = { snapshot, fingerprint, setConfirmed, watch };
})();
