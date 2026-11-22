// Smart Apply entry points, called by the service worker (through chrome.scripting) and by the review panel.
// The work is done by the modules loaded before this file: dom, fieldmap, scan, fill, resume, review, submit.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.core) return;
  const { visible, textOf, setNativeValue, safeClick, waitFor } = JP.dom;
  const { scan, labelFor, currentValue } = JP.scan;
  const { fill, useProposed, keyFor } = JP.filler;

  function adapterHere() {
    const host = location.hostname;
    const named = Object.values(JP.adapters).filter((a) => !a.generic);
    return named.find((a) => a.matchesHost(host) && a.isApplicationPage())
      || (JP.allowGeneric ? (JP.adapters.generic?.isApplicationPage() ? JP.adapters.generic : null) : null);
  }

  // Back-compatible namespace (tests and adapters use it).
  JP.core = { scan, fill, visible, labelFor, textOf, setNativeValue, safeClick, matchOption: JP.fieldmap.matchOption, currentValue, waitFor,
              adapterHere, keyFor };

  JP.detect = () => {
    const a = adapterHere();
    if (!a) return { url: location.href, platform: null };
    const qs = scan(a);
    return {
      url: location.href, platform: a.name, title: a.jobTitle?.() || null, company: a.company?.() || null,
      fields: qs.filter((q) => q.kind !== "file").length,
      questions: qs.filter((q) => q.kind !== "file" && q.label).filter((q) => { const c = keyFor(a, q); return !c.never && !(c.key && c.confidence >= 0.4); }).map((q) => q.label),
      // What the form itself says about each question: required | optional (anything else is unknown, never optional).
      requirements: Object.fromEntries(qs.filter((q) => q.kind !== "file" && q.label && q.requirement !== "unknown").map((q) => [q.label, q.requirement])),
      resumeField: Boolean(a.resumeInput?.()), resumeAttached: Boolean(a.hasResume?.()), resumeFirst: Boolean(a.resumeFirst),
      assistedSubmit: Boolean(a.assistedSubmit), step: a.step?.() || null, confirmation: JP.submit.confirmation(a),
    };
  };

  JP.fill = async (payload) => {
    const a = adapterHere();
    if (!a) return { error: "This page is not a supported application form." };
    JP.context = { ...(JP.context || {}), ...(payload.context || {}) };
    const report = await fill(a, payload);
    JP.panel?.show(report, a);
    return report;
  };

  JP.attachResume = async (file, opts) => {
    const a = adapterHere();
    if (!a) return { ok: false, reason: "This page is not a supported application form." };
    const res = await JP.resume.attach(a, file, opts);
    file.b64 = null;  // drop the bytes from this script's memory
    JP.panel?.resumeResult?.(res);
    return res;
  };

  JP.snapshot = () => {
    const a = adapterHere();
    return a ? JP.review.snapshot(a, JP.context || {}) : null;
  };

  /** After a navigation (e.g. Lever's /thanks page): is there a confirmation here? Used by the service worker. */
  JP.checkOutcome = () => {
    const a = adapterHere() || Object.values(JP.adapters).find((x) => !x.generic && x.matchesHost(location.hostname)) || JP.adapters.generic;
    const c = a ? JP.submit.confirmation(a) : null;
    if (c) return { outcome: "confirmed", signal: c.signal, signal_kind: c.kind };
    if (!a?.isApplicationPage?.()) return { outcome: "uncertain" };
    // Back on the form after submitting: the employer's validation messages, if it shows any.
    const errors = JP.submit.submitErrors(a);
    return errors.length ? { outcome: "errors", errors } : { outcome: "still_on_form" };
  };

  JP.useProposed = useProposed;
})();
