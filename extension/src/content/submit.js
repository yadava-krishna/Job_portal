// Submission: only ever after the user explicitly authorised this one application, and only on platforms whose
// adapter supports assisted submission. Never because a form was filled.
//
//   Mode A (autofill and review): the user clicks the site's own submit button. JobPilot notices the submission and
//                                 watches for the employer's confirmation.
//   Mode B (assisted submission): in the review panel the user ticks "I reviewed this application" and clicks
//                                 "Submit this application" (a real, trusted click). JobPilot re-reads the form; if it
//                                 changed since the review it refuses, otherwise it clicks the site's submit button once.
// CAPTCHAs, OTPs and bot checks are never touched: if one appears, the user completes it and JobPilot keeps watching.
// "Submitted" is reported only on a confirmation signal (success page/text); otherwise the outcome is "uncertain".
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.submit) return;
  const { clean, sleep, visible, textOf } = JP.dom;

  const SUCCESS_TEXT = /(thank(s| you) for (applying|your application|submitting)|application (has been |was )?(submitted|received|sent)|we('|’)ve received your application|your application is (complete|in)|successfully (applied|submitted))/i;
  const SUCCESS_URL = /\/(thanks|thank-you|thankyou|confirmation|application-submitted|success)(\/|$|\?)/i;

  function submitButton(adapter) {
    const own = adapter.submitButton?.();
    if (own !== undefined) return own;
    const root = adapter.root() || document.body;
    const cands = [...root.querySelectorAll("button[type=submit], input[type=submit], button:not([type])")]
      .filter((b) => visible(b) && !b.disabled && /submit|apply/i.test(clean(b.textContent || b.value)));
    return cands.length === 1 ? cands[0] : null;
  }

  /** A confirmation signal on the current page, or null: {signal, kind} where kind says what matched:
   *  "adapter" (the platform's own confirmation check), "url" (a confirmation address) or "text" (page text only). */
  function confirmation(adapter) {
    const own = adapter.confirmation?.();
    if (own) return { ...own, kind: "adapter" };
    if (SUCCESS_URL.test(location.pathname)) return { signal: `Confirmation page (${location.pathname})`, kind: "url" };
    const main = document.querySelector("main, [role=main], #content, body");
    const t = textOf(main).slice(0, 20000);
    const m = SUCCESS_TEXT.exec(t);
    if (m && !(adapter.isApplicationPage?.() && submitButton(adapter))) return { signal: `Page says: "${m[0]}"`, kind: "text" };
    return null;
  }

  /** Visible validation errors after a submit attempt (the site refused it). */
  function submitErrors(adapter) {
    const own = adapter.submitErrors?.();
    if (own?.length) return own;
    const root = adapter.root() || document.body;
    return [...root.querySelectorAll("[aria-invalid='true'], [role=alert], .error:not(:empty), [class*='error-message']")]
      .filter(visible).map((e) => (e.matches("input,select,textarea") ? (JP.scan.labelFor(e, adapter) || "A field") + " is invalid" : textOf(e)))
      .filter(Boolean).slice(0, 8);
  }

  /** Watch for the outcome after a submission: {outcome: confirmed|errors|uncertain, signal?, signal_kind?, errors?}. */
  async function outcome(adapter, { timeoutMs = 30000, step = 400 } = {}) {
    const started = Date.now();
    await sleep(Math.min(800, timeoutMs));
    while (Date.now() - started < timeoutMs) {
      const c = confirmation(adapter);
      if (c) return { outcome: "confirmed", signal: c.signal, signal_kind: c.kind };
      const errs = submitErrors(adapter);
      if (errs.length && Date.now() - started > 1500) return { outcome: "errors", errors: errs };
      await sleep(step);
    }
    return { outcome: "uncertain" };
  }

  // One authorisation buys one click, within a few seconds of the user's trusted click in the panel.
  let grant = null;
  function authorize(fingerprint, trusted) {
    if (!trusted) return false;
    grant = { fingerprint, at: Date.now() };
    return true;
  }

  /** Click the site's submit button once, if and only if a fresh grant matches the form as it is now. */
  function clickSubmit(adapter) {
    if (!adapter.assistedSubmit) return { ok: false, reason: `Assisted submission is not available on ${adapter.name}. Submit on the page yourself.` };
    const g = grant; grant = null;
    if (!g || Date.now() - g.at > 15000) return { ok: false, reason: "Submission was not authorised. Review the application and click Submit again." };
    const snap = JP.review.snapshot(adapter);
    if (snap.fingerprint !== g.fingerprint) return { ok: false, stale: true, reason: "The form changed after your review. Review it again." };
    if (!snap.ready) return { ok: false, reason: "Some required answers are missing or invalid. Fix them first." };
    if (snap.validation.confirm.length) return { ok: false, reason: `Tick the answers you checked: ${snap.validation.confirm.join(", ")}.` };
    const btn = submitButton(adapter);
    if (!btn) return { ok: false, reason: "JobPilot could not find a single submit button on this page. Submit it yourself." };
    btn.click();
    return { ok: true };
  }

  /** Mode A: tell `onSubmit` when the user submits the form themselves (only real user actions count). */
  function watchUserSubmit(adapter, onSubmit) {
    const root = adapter.root() || document.body;
    const onClick = (e) => {
      if (!e.isTrusted) return;
      const btn = submitButton(adapter);
      if (btn && (e.target === btn || btn.contains(e.target))) onSubmit("click");
    };
    // (A submit event caused by JobPilot's own authorised click is also "trusted", so the panel stops this watcher
    // before an assisted submission.)
    const onFormSubmit = (e) => { if (e.isTrusted) onSubmit("submit"); };
    const formEl = root.closest?.("form") || root.querySelector?.("form") || root;
    document.addEventListener("click", onClick, true);
    formEl.addEventListener("submit", onFormSubmit, true);
    return () => { document.removeEventListener("click", onClick, true); formEl.removeEventListener("submit", onFormSubmit, true); };
  }

  JP.submit = { submitButton, confirmation, submitErrors, outcome, authorize, clickSubmit, watchUserSubmit, SUCCESS_TEXT, SUCCESS_URL };
})();
