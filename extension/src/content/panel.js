// Smart Apply review panel: a side-docked overlay in a closed Shadow DOM (the page's CSS and scripts cannot restyle
// or read it). Buttons only react to real user clicks (event.isTrusted), never to events a page script dispatches.
//
// It shows the application as the form holds it right now: job, personal and professional details, documents,
// screening answers (with where each answer came from), and what still needs the user. It can be collapsed to a
// small tab, moved to the other side of the window so it never hides a field, and closed.
// After a Fill it can offer to save answers the user typed on the form for next time: nothing is saved unless the user
// ticks it and clicks "Save selected"; sensitive, consent, password and file fields are never offered.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.panel) return;
  let host = null; let shadow = null; let adapter = null; let lastReport = null;
  const ui = { side: "right", collapsed: false, tab: "review", reviewed: null, stale: false, stopWatch: null, stopSubmitWatch: null,
               phase: null, message: null, resume: null, busy: false,
               learnPicks: new Map(), learned: new Set(), learnResult: null };

  JP.bridge ??= {
    send: (action, args = {}) => new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: `panel:${action}`, args }, (r) => resolve(r ?? { ok: false, error: chrome.runtime.lastError?.message || "No response" }));
      } catch { resolve({ ok: false, error: "The extension was updated or reloaded. Reload this page." }); }
    }),
  };

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .p { position: fixed; z-index: 2147483646; top: 12px; bottom: 12px; width: min(400px, calc(100vw - 24px));
         display: flex; flex-direction: column; font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: #111827;
         background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 12px 40px rgba(0,0,0,.18); overflow: hidden; }
    .p.right { right: 12px; } .p.left { left: 12px; }
    .pill { position: fixed; z-index: 2147483646; bottom: 16px; padding: 8px 12px; border-radius: 999px; background: #4338ca; color: #fff;
            font: 600 12px system-ui, sans-serif; border: 0; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,.2); }
    .pill.right { right: 16px; } .pill.left { left: 16px; }
    header { display: flex; align-items: center; gap: 6px; padding: 10px 12px; background: #312e81; color: #fff; }
    header .t { flex: 1; min-width: 0; } header b { display: block; font-size: 13px; }
    header small { opacity: .85; font-size: 11px; }
    button { font: inherit; cursor: pointer; border-radius: 7px; border: 1px solid #d1d5db; background: #fff; color: #111827; padding: 4px 9px; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    button.primary { background: #4338ca; border-color: #4338ca; color: #fff; font-weight: 600; }
    button.ghost { border-color: rgba(255,255,255,.45); background: transparent; color: #fff; padding: 2px 7px; }
    button:focus-visible, input:focus-visible { outline: 2px solid #6366f1; outline-offset: 2px; }
    .tabs { display: flex; border-bottom: 1px solid #e5e7eb; }
    .tabs button { flex: 1; border: 0; border-radius: 0; padding: 8px; background: transparent; color: #4b5563; }
    .tabs button[aria-selected=true] { color: #312e81; font-weight: 600; box-shadow: inset 0 -2px 0 #4338ca; }
    .body { overflow: auto; padding: 8px 12px 12px; flex: 1; }
    .job { padding: 8px 12px; border-bottom: 1px solid #f3f4f6; }
    .job .ttl { font-weight: 600; } .muted { color: #6b7280; font-size: 12px; }
    .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
    .chip { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: #eef2ff; color: #3730a3; }
    .chip.warn { background: #fef3c7; color: #92400e; } .chip.bad { background: #fee2e2; color: #991b1b; } .chip.ok { background: #d1fae5; color: #065f46; }
    h4 { margin: 12px 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { padding: 6px 0; border-bottom: 1px solid #f3f4f6; }
    li:last-child { border-bottom: 0; }
    .row { display: flex; gap: 8px; align-items: baseline; justify-content: space-between; }
    .l { font-weight: 600; } .v { color: #111827; word-break: break-word; } .v.empty { color: #9ca3af; font-style: italic; }
    .src { font-size: 11px; color: #6b7280; } .src.user { color: #1d4ed8; } .src.suggested { color: #b45309; }
    .prob { font-size: 12px; color: #b91c1c; }
    .ok .l::before { content: "✓ "; color: #059669; } .rv .l::before { content: "● "; color: #d97706; } .nd .l::before { content: "! "; color: #dc2626; }
    .box { margin: 8px 0; padding: 8px 10px; border-radius: 8px; background: #f9fafb; border: 1px solid #e5e7eb; }
    .box.warn { background: #fffbeb; border-color: #fcd34d; } .box.bad { background: #fef2f2; border-color: #fca5a5; } .box.ok { background: #ecfdf5; border-color: #6ee7b7; }
    .box.info { background: #eef2ff; border-color: #c7d2fe; color: #312e81; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    label.tick { display: flex; gap: 6px; align-items: flex-start; font-size: 12px; margin-top: 4px; }
    .foot { padding: 8px 12px; border-top: 1px solid #f3f4f6; display: flex; flex-direction: column; gap: 6px; }
    .r { color: #4b5563; font-size: 12px; }
    @media (prefers-color-scheme: dark) {
      .p { background: #0f172a; color: #f1f5f9; border-color: #334155; }
      li, .job, .tabs, .foot { border-color: #1e293b; } .muted, .r, .src { color: #94a3b8; } .v { color: #e2e8f0; }
      button { background: #1e293b; color: #f1f5f9; border-color: #475569; } button.primary { background: #4f46e5; border-color: #4f46e5; }
      .box { background: #111827; border-color: #334155; } .box.warn { background: #422006; border-color: #a16207; } .box.bad { background: #450a0a; border-color: #b91c1c; }
      .box.ok { background: #052e16; border-color: #15803d; } .box.info { background: #1e1b4b; border-color: #4338ca; color: #c7d2fe; }
      .chip { background: #1e1b4b; color: #c7d2fe; } .tabs button { color: #94a3b8; } .tabs button[aria-selected=true] { color: #c7d2fe; }
    }`;

  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), (ev) => { if (ev.isTrusted || JP.__testing) v(ev); });
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) e.append(k);
    return e;
  }

  function mount() {
    if (host?.isConnected) return;
    host = document.createElement("jobpilot-review");
    shadow = host.attachShadow({ mode: JP.__testing ? "open" : "closed" });
    document.documentElement.append(host);
    JP.__panelRoot = JP.__testing ? shadow : null;
  }

  const ctx = () => JP.context || {};
  const snapshot = () => (adapter ? JP.review.snapshot(adapter, ctx()) : null);

  // ---- rendering --------------------------------------------------------------------------

  function listSection(title, cls, items, extra) {
    if (!items?.length) return null;
    return el("div", {}, el("h4", {}, `${title} (${items.length})`),
      el("ul", { class: cls }, ...items.map((i) => {
        const li = el("li", {}, el("div", { class: "l" }, i.label));
        const why = i.reason || i.note || (i.value ? `Filled: ${String(i.value).slice(0, 80)}` : "");
        if (why) li.append(el("div", { class: "r" }, why));
        extra?.(i, li);
        return li;
      })));
  }

  function useButton(i) {
    const b = el("button", { type: "button", onclick: async () => {
      b.disabled = true;
      b.textContent = (await JP.useProposed(i.ref)) ? "Done" : "Could not fill";
      render();
    } }, "Use JobPilot value");
    return b;
  }

  // ---- "Save answers for next time" --------------------------------------------------------------

  const learnKey = (c) => `${c.label}\u0000${c.value}`;
  const learnCandidates = () => (adapter && lastReport ? JP.review.learnable(adapter, lastReport) : []).filter((c) => !ui.learned.has(learnKey(c)));
  const learnChecked = (c) => (ui.learnPicks.has(c.ref) ? ui.learnPicks.get(c.ref) : c.checked);

  function learnSection() {
    const cands = learnCandidates();
    const res = ui.learnResult;
    if (!cands.length && !res) return null;
    const box = el("div", { class: "box", "data-section": "learn" }, el("strong", {}, "Save answers for next time"));
    if (cands.length) {
      box.append(el("div", { class: "r" }, "Answers you gave on this form. Tick the ones JobPilot may reuse; nothing is saved until you click Save selected."));
      for (const c of cands) {
        const tick = el("input", { type: "checkbox", "aria-label": `Save: ${c.label}`, "data-ref": c.ref });
        tick.checked = learnChecked(c);
        tick.addEventListener("change", (e) => { if (!e.isTrusted && !JP.__testing) { tick.checked = !tick.checked; return; } ui.learnPicks.set(c.ref, tick.checked); });
        box.append(el("label", { class: "tick" }, tick, el("span", {}, el("span", { class: "l" }, c.label), " ", el("span", { class: "v" }, `"${c.value.slice(0, 120)}"`),
          c.sensitive ? el("span", { class: "src" }, " (private: kept encrypted)") : null)));
      }
      box.append(el("div", { class: "actions" }, el("button", { type: "button", disabled: ui.busy, onclick: saveAnswers }, "Save selected")));
    }
    if (res?.error) box.append(el("div", { class: "prob", role: "status" }, res.error));
    if (res?.saved?.length) box.append(el("div", { class: "src", role: "status" }, `Saved for next time: ${res.saved.join(", ")}.`));
    for (const e of res?.errors || []) box.append(el("div", { class: "prob" }, `Not saved: ${e.question}: ${e.error}`));
    return box;
  }

  async function saveAnswers() {
    // Re-read the form now: send exactly what the page holds for each ticked question.
    const items = learnCandidates().filter(learnChecked).map((c) => ({ question: c.label, answer: c.value, key: learnKey(c) }));
    if (!items.length) { ui.learnResult = { error: "Tick at least one answer to save." }; render(); return; }
    ui.busy = true; render();
    const r = await JP.bridge.send("learn", { items: items.map(({ question, answer }) => ({ question, answer })) });
    ui.busy = false;
    if (!r.ok) ui.learnResult = { error: r.error || "Could not save." };
    else {
      const saved = new Set(r.data?.saved || []);
      for (const i of items) if (saved.has(i.question)) ui.learned.add(i.key);
      ui.learnResult = { saved: r.data?.saved || [], errors: r.data?.errors || [] };
    }
    render();
  }

  function fillTab() {
    const r = lastReport;
    if (!r) return [el("p", { class: "muted" }, "Click Fill to start.")];
    const parts = [
      listSection("Needs your input", "nd", r.needs),
      listSection("Not sure: check first", "rv", r.unsure, (i, li) => { li.append(el("div", { class: "r" }, `JobPilot value: ${String(i.proposed).slice(0, 80)}`)); if (i.replaceable) li.append(useButton(i)); }),
      listSection("Please review", "rv", r.review),
      listSection("Filled", "ok", r.filled),
      listSection("Kept your existing value", "rv", r.kept, (i, li) => { if (i.replaceable) li.append(useButton(i)); }),
      listSection("Skipped", "", r.skipped),
      learnSection(),
    ].filter(Boolean);
    return parts.length ? parts : [el("p", {}, "No fillable questions were found on this part of the form.")];
  }

  function item(i) {
    const li = el("li", {},
      el("div", { class: "row" }, el("span", { class: "l" }, i.label), i.required ? el("span", { class: "chip warn" }, "Required") : null),
      el("div", { class: i.value ? "v" : "v empty" }, i.value ? String(i.value).slice(0, 300) : "Not answered"),
      el("div", { class: `src ${i.sourceKind}` }, i.source));
    if (i.note) li.append(el("div", { class: "r" }, i.note));
    if (i.problem) li.append(el("div", { class: "prob" }, i.problem));
    if (i.confirm && i.value) {
      const box = el("input", { type: "checkbox", "aria-label": `I checked: ${i.label}`, "data-confirmed": i.confirmed ? "yes" : "no" });
      box.checked = i.confirmed;
      box.addEventListener("change", (e) => { if (!e.isTrusted && !JP.__testing) { box.checked = !box.checked; return; } JP.review.setConfirmed(i.ref, box.checked); render(); });
      li.append(el("label", { class: "tick" }, box, el("span", {}, "I checked this answer (it commits you, e.g. salary, notice period or work authorisation)")));
    }
    return li;
  }

  function group(title, items) {
    return items?.length ? el("div", {}, el("h4", {}, title), el("ul", {}, ...items.map(item))) : null;
  }

  function reviewTab(s) {
    if (!s) return [el("p", { class: "muted" }, "The application form is no longer on this page.")];
    const v = s.validation;
    const out = [];
    if (s.step?.title) out.push(el("div", { class: "box info" }, `Step ${s.step.index ?? "?"}${s.step.total ? ` of ${s.step.total}` : ""}: ${s.step.title}`,
      s.step.final ? null : el("div", { class: "r" }, "Fill and check this step, then continue on the page. JobPilot will offer to fill the next step.")));
    const problems = [...v.missing.map((m) => `Missing: ${m}`), ...v.invalid, ...v.uploadErrors];
    if (problems.length) out.push(el("div", { class: "box bad" }, el("strong", {}, "Fix before submitting"), el("ul", {}, ...problems.map((p) => el("li", {}, p)))));
    if (v.confirm.length) out.push(el("div", { class: "box warn" }, `Tick each answer you checked: ${v.confirm.join(", ")}.`));
    if (v.warnings.length) out.push(el("div", { class: "box warn" }, el("ul", {}, ...v.warnings.map((w) => el("li", {}, w)))));
    const docs = s.documents.map((d) => el("li", {},
      el("div", { class: "row" }, el("span", { class: "l" }, d.label), el("span", { class: `chip ${d.error ? "bad" : d.attached ? "ok" : d.required ? "warn" : ""}` }, d.error ? "Upload problem" : d.attached ? "Attached" : d.required ? "Required" : "Optional")),
      el("div", { class: d.files.length ? "v" : "v empty" }, d.files.length ? d.files.map((f) => `${f.name} (${Math.round(f.size / 1024)} KB)`).join(", ") : d.attached ? "Attached (shown by the site)" : "No file"),
      d.error ? el("div", { class: "prob" }, d.error) : null,
      d.isResume ? el("div", { class: "actions" }, el("button", { type: "button", onclick: () => attach(d.attached) }, d.attached ? "Replace with my JobPilot resume" : "Attach my JobPilot resume"),
        ui.resume ? el("span", { class: "muted" }, `Chosen: ${ui.resume}`) : null) : null));
    out.push(group("Personal", s.personal), group("Professional", s.professional),
      docs.length ? el("div", {}, el("h4", {}, "Documents"), el("ul", {}, ...docs)) : null,
      group("Questions", s.screening), learnSection());
    return out.filter(Boolean);
  }

  function submitArea(s) {
    const c = ctx();
    const nodes = [];
    if (ui.phase === "pending") return [el("div", { class: "box info", role: "status" }, "Waiting for the employer's confirmation… Complete any check the site shows (for example a CAPTCHA) yourself.")];
    if (ui.phase === "confirmed") return [el("div", { class: "box ok", role: "status" }, el("strong", {}, "Submitted (confirmed)"), el("div", { class: "r" }, ui.message || ""))];
    if (ui.phase === "uncertain") {
      return [el("div", { class: "box warn", role: "status" }, el("strong", {}, "JobPilot could not see a confirmation."),
        el("div", { class: "r" }, "Check the page or your email. Did the application go through?"),
        el("div", { class: "actions" },
          el("button", { type: "button", class: "primary", onclick: () => userConfirm(true) }, "Yes, it was submitted"),
          el("button", { type: "button", onclick: () => userConfirm(false) }, "No, it was not")))];
    }
    if (ui.message) nodes.push(el("div", { class: `box ${ui.messageKind || "warn"}`, role: "status" }, ui.message));
    if (!s) return nodes;
    if (s.step && !s.step.final) return nodes;
    const reviewedNow = ui.reviewed && ui.reviewed === s.fingerprint && !ui.stale;
    if (ui.stale) nodes.push(el("div", { class: "box warn", role: "status" }, "The form changed after your review. Review it again before submitting."));
    nodes.push(el("button", { type: "button", disabled: !s.ready || s.validation.confirm.length > 0 || ui.busy, onclick: markReviewed },
      reviewedNow ? "Reviewed ✓ (review again)" : "I have reviewed this application"));
    if (adapter?.assistedSubmit && c.applicationId) {
      nodes.push(el("button", { type: "button", class: "primary", disabled: !reviewedNow || !s.ready || s.validation.confirm.length > 0 || ui.busy,
        onclick: (e) => assistedSubmit(e) }, "Submit this application"));
      nodes.push(el("div", { class: "r" }, "JobPilot clicks the site's submit button once, only after you click here. Or submit on the page yourself."));
    } else {
      nodes.push(el("div", { class: "r" }, c.applicationId ? `Submit on the page yourself when you are ready. JobPilot watches for the confirmation and records it.`
        : "This job is not in your JobPilot jobs, so it will not be tracked. Submit on the page yourself."));
    }
    return nodes;
  }

  // The application's tracked state (from JobPilot). While filling, the live check of the form below says more and is
  // newer, so the fill-progress states are not repeated next to it; later states (reviewed, pending...) are shown.
  const FILL_PROGRESS = ["Filling", "Needs information", "Ready for review"];
  function trackedChip(label, s) {
    if (!label || (s && FILL_PROGRESS.includes(label))) return null;
    return el("span", { class: "chip", title: "This application's status in JobPilot" }, `JobPilot: ${label}`);
  }

  function render() {
    if (!adapter) return;
    mount();
    shadow.replaceChildren();
    if (ui.collapsed) {
      shadow.append(el("style", {}, CSS), el("button", { type: "button", class: `pill ${ui.side}`, "aria-label": "Open JobPilot review", onclick: () => { ui.collapsed = false; render(); } }, "JobPilot ▸ Review"));
      return;
    }
    const s = snapshot();
    const r = lastReport;
    const c = ctx();
    const counts = r ? `${r.filled.length} filled · ${r.review.length + (r.unsure?.length || 0)} to check · ${r.needs.length} need you` : "";
    const head = el("header", {},
      el("div", { class: "t" }, el("b", {}, "JobPilot Smart Apply"), el("small", {}, counts)),
      el("button", { type: "button", class: "ghost", "aria-label": `Move panel to the ${ui.side === "right" ? "left" : "right"}`, onclick: () => { ui.side = ui.side === "right" ? "left" : "right"; render(); } }, ui.side === "right" ? "◂" : "▸"),
      el("button", { type: "button", class: "ghost", "aria-label": "Collapse", onclick: () => { ui.collapsed = true; render(); } }, "–"),
      el("button", { type: "button", class: "ghost", "aria-label": "Close", onclick: close }, "✕"));
    const job = el("div", { class: "job" },
      el("div", { class: "ttl" }, s?.job.title || c.job?.title || "Application form"),
      el("div", { class: "muted" }, [s?.job.company || c.job?.company, s?.job.location || c.job?.location, s?.platform].filter(Boolean).join(" · ")),
      el("div", { class: "chips" },
        trackedChip(c.stateLabel, s),
        s ? el("span", { class: `chip ${s.ready ? "ok" : "warn"}` }, s.ready ? "Required answers complete" : "Needs information") : null,
        adapter.assistedSubmit ? el("span", { class: "chip" }, "Assisted submit available") : el("span", { class: "chip" }, "You submit on the page")));
    const tabBtn = (id, text) => el("button", { type: "button", role: "tab", "aria-selected": String(ui.tab === id), onclick: () => { ui.tab = id; render(); } }, text);
    const body = el("div", { class: "body", role: "tabpanel" }, ...(ui.tab === "review" ? reviewTab(s) : fillTab()));
    if (ui.notice) body.prepend(el("div", { class: "box info", role: "status" }, ui.notice));
    const foot = el("div", { class: "foot" },
      el("div", { class: "actions" },
        el("button", { type: "button", disabled: ui.busy, onclick: refill }, "Fill again"),
        el("button", { type: "button", onclick: () => { ui.notice = null; render(); } }, "Re-check form"),
        el("button", { type: "button", onclick: () => JP.bridge.send("openApp") }, "Open JobPilot")),
      ...submitArea(s));
    shadow.append(el("style", {}, CSS), el("div", { class: `p ${ui.side}`, role: "dialog", "aria-label": "JobPilot Smart Apply review" },
      head, job, el("div", { class: "tabs", role: "tablist" }, tabBtn("review", "Review"), tabBtn("fill", "What JobPilot did")), body, foot));
  }

  // ---- actions ------------------------------------------------------------------------------

  function close() {
    ui.stopWatch?.(); ui.stopSubmitWatch?.();
    host?.remove(); host = null;
  }

  async function refill() {
    ui.busy = true; render();
    const r = await JP.bridge.send("fill");
    ui.busy = false;
    if (!r.ok) ui.message = r.error, ui.messageKind = "bad";
    render();
  }

  async function attach(replace) {
    ui.busy = true; render();
    const r = await JP.bridge.send("attachResume", { replace: Boolean(replace) });
    ui.busy = false;
    if (!r.ok) { ui.message = r.error; ui.messageKind = "bad"; }
    render();
  }

  async function markReviewed() {
    const s = snapshot();
    if (!s?.ready) return;
    ui.reviewed = s.fingerprint; ui.stale = false; ui.message = null;
    ui.stopWatch?.();
    ui.stopWatch = JP.review.watch(adapter, s.fingerprint, () => {
      if (ui.stale) return;
      ui.stale = true;
      JP.bridge.send("state", { state: "ready_for_review", session: { fingerprint: null, message: "The form changed after review." } });
      render();
    });
    await JP.bridge.send("state", { state: "reviewed", session: { fingerprint: s.fingerprint, counts: countsOf(s) } });
    render();
  }

  const countsOf = (s) => ({ filled: s.counts.filled, needs: s.validation.missing.length, review: s.validation.warnings.length });

  async function assistedSubmit(e) {
    const s = snapshot();
    if (!s || s.fingerprint !== ui.reviewed || ui.stale) { ui.stale = true; render(); return; }
    if (!JP.submit.authorize(s.fingerprint, e.isTrusted || JP.__testing)) return;
    ui.busy = true; render();
    const auth = await JP.bridge.send("state", { state: "submission_authorized", mode: "assisted_submit", session: { fingerprint: s.fingerprint } });
    if (!auth.ok) { ui.busy = false; ui.message = auth.error; ui.messageKind = "bad"; render(); return; }
    ui.stopSubmitWatch?.(); ui.stopSubmitWatch = null;  // our own click must not be reported as a second (user) submission
    // Record the attempt BEFORE clicking: many forms post and navigate at once, which ends this script, and the service
    // worker can only check the next page for a confirmation if it already knows a submission was attempted.
    const pend = await JP.bridge.send("state", { state: "submission_pending", mode: "assisted_submit",
                                                 session: { message: "Submitted by Smart Apply after your authorisation." } });
    if (!pend.ok) { ui.busy = false; ui.message = pend.error; ui.messageKind = "bad"; render(); return; }
    ui.phase = "pending";
    ui.reported = true;
    const res = JP.submit.clickSubmit(adapter);
    ui.busy = false;
    if (!res.ok) {
      if (res.stale) ui.stale = true;
      ui.phase = null; ui.reported = false;
      ui.message = res.reason; ui.messageKind = "bad";
      await JP.bridge.send("state", { state: "ready_for_review", session: { message: res.reason } });
      render();
      return;
    }
    await afterSubmit("assisted_submit", { recorded: true });
  }

  async function afterSubmit(mode, { recorded = false } = {}) {
    if (ui.reported && !recorded) return;  // one outcome per submission
    ui.reported = true;
    ui.phase = "pending"; render();
    if (!recorded) await JP.bridge.send("state", { state: "submission_pending", mode, session: { message: "You submitted on the page." } });
    const o = await JP.submit.outcome(adapter, { timeoutMs: JP.__outcomeTimeout ?? 30000 });
    if (o.outcome === "confirmed") { ui.phase = "confirmed"; ui.message = o.signal; }
    else if (o.outcome === "errors") { ui.phase = null; ui.reported = false; ui.message = `The site did not accept the submission: ${o.errors.join("; ")}`; ui.messageKind = "bad"; ui.reviewed = null; }
    else ui.phase = "uncertain";
    await JP.bridge.send("outcome", o);
    render();
  }

  async function userConfirm(submitted) {
    const r = await JP.bridge.send("confirm", { submitted });
    ui.phase = submitted && r.ok ? "confirmed" : null;
    ui.message = submitted ? "Recorded as submitted (you confirmed it)." : "Recorded as not submitted.";
    ui.messageKind = "info";
    render();
  }

  // ---- entry points -------------------------------------------------------------------------

  function show(report, a) {
    adapter = a || adapter;
    lastReport = report;
    ui.learnPicks.clear(); ui.learnResult = null;
    ui.tab = report && (report.needs.length || report.unsure?.length) ? "fill" : "review";
    ui.notice = null;
    if (!ui.stopSubmitWatch && adapter && ctx().applicationId) {
      ui.stopSubmitWatch = JP.submit.watchUserSubmit(adapter, () => { if (ui.phase !== "pending") afterSubmit("autofill_review"); });
    }
    render();
  }

  function notice(text) { ui.notice = text; render(); }

  function stepChanged(step) {
    ui.reviewed = null; ui.stale = false;
    ui.notice = `New step: ${step?.title || "next page"}. Click Fill again to fill it.`;
    lastReport = null; ui.tab = "review";
    JP.bridge.send("state", { state: "filling", session: { step: step?.title || null } });
    render();
  }

  function resumeResult(res) {
    if (res?.ok) { ui.resume = res.name; ui.message = `Resume attached and checked: ${res.name} (${Math.round(res.size / 1024)} KB).`; ui.messageKind = "ok"; }
    else if (res) { ui.message = res.reason; ui.messageKind = "bad"; }
    render();
  }

  JP.panel = { show, notice, stepChanged, resumeResult, render, close, _ui: ui };
})();
