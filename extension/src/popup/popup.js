// Popup UI. Talks only to the extension's service worker. All page data is rendered with textContent.

const WEB_APP = "https://yadava-krishna.github.io/Job_portal/";
const app = document.getElementById("app");
// Normally the popup acts on the active tab. Opened as a page with ?tab=<id>, it acts on that tab instead.
const TARGET_TAB = Number.parseInt(new URLSearchParams(location.search).get("tab") ?? "", 10);
const who = document.getElementById("who");

const send = (action, args = {}) =>
  new Promise((resolve) => chrome.runtime.sendMessage({ action, args }, (r) => resolve(r ?? { ok: false, error: chrome.runtime.lastError?.message || "No response" })));

function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k);
  return e;
}

const note = (cls, ...kids) => h("div", { class: `note ${cls}` }, ...kids);
const openWeb = (path = "") => chrome.tabs.create({ url: WEB_APP + (path ? `#/${path}` : "") });
const linkTo = (text, path) => h("button", { type: "button", class: "link", onclick: () => openWeb(path) }, text);
function show(...nodes) { app.replaceChildren(...nodes.filter((n) => n != null && n !== false)); }  // replaceChildren(null) would print "null"
function busy(btn, text) { btn.disabled = true; const t = btn.textContent; btn.textContent = text; return () => { btn.disabled = false; btn.textContent = t; }; }

// ---- connect -----------------------------------------------------------------------------------

function connectView(error) {
  const code = h("input", { type: "text", class: "code", maxlength: "9", placeholder: "XXXX-XXXX", autocomplete: "off", spellcheck: "false", "aria-label": "Connection code" });
  const device = h("input", { type: "text", value: `Chrome on ${navigator.userAgentData?.platform || "this computer"}`, maxlength: "100", "aria-label": "Name for this browser" });
  const msg = h("div");
  const btn = h("button", { type: "submit", class: "primary" }, "Connect");
  const form = h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault();
    const done = busy(btn, "Connecting…");
    const r = await send("pair", { code: code.value, deviceName: device.value });
    done();
    if (r.ok) return main();
    msg.replaceChildren(note("bad", r.error));
  } },
  h("h2", {}, "Connect to JobPilot"),
  h("p", { class: "muted" }, "In JobPilot open Settings → Browser extension, create a connection code and type it here. You never enter your password in the extension."),
  code, h("label", { class: "muted" }, "Name for this browser"), device, btn, msg);
  show(error ? note("bad", error) : null, form, h("p", {}, linkTo("Open JobPilot Settings", "settings?tab=extension")));
  code.focus();
}

// ---- main -------------------------------------------------------------------------------------

async function main() {
  show(h("p", { class: "muted" }, "Checking this page…"));
  const st = await send("state");
  if (!st.ok) return show(note("bad", st.error));
  if (!st.data.connected) { who.textContent = ""; return connectView(st.data.error); }
  who.textContent = st.data.status?.user_display_name || st.data.info?.user || "";
  if (st.data.error) return show(note("bad", st.data.error), h("button", { type: "button", onclick: main }, "Try again"));

  const insp = await send("inspect", Number.isInteger(TARGET_TAB) ? { tabId: TARGET_TAB } : {});
  if (!insp.ok) return show(note("bad", insp.error));
  const d = insp.data;
  const missing = st.data.status?.missing || [];
  if (d.blocked) return handoffView(d.blocked);
  if (!d.supported) {
    if (d.canRequest) return permissionView(d.canRequest);
    return show(
      h("h2", {}, "Not an application page"),
      h("p", {}, "Smart Apply works on employer application forms: Greenhouse, Lever and Ashby out of the box, and Workday, iCIMS, SuccessFactors, Taleo and other employer sites once you allow them."),
      missingCard(missing));
  }
  if (!d.form) return noFormView(d);
  formView(d, missing);
}

/** No application form recognised: say why, from what the page actually holds, and what to do next. */
function noFormView(d) {
  const g = d.diagnostics || { reason: "no_fields" };
  const again = h("button", { type: "button", onclick: main }, "Check again");
  const apply = d.platform === "SmartRecruiters" ? "I'm interested" : "Apply";
  const why = {
    no_fields: `No application form is on this page yet. Click “${apply}” on the page; when the form shows, click Check again.`,
    fields_unrecognised: `JobPilot can see ${g.lightFields + g.deepFields} field${g.lightFields + g.deepFields === 1 ? "" : "s"} here but none asks for your name or e-mail, so it isn't treated as an application form. If the form is further down or on the next step, go there and click Check again.`,
    closed_components: "This page builds its form from components the extension isn't allowed to read, so JobPilot can't fill it. Use Download resume and fill it yourself, then record the application in JobPilot.",
    frame: `The form is inside a frame from ${g.frameHost}. Allow Smart Apply on that site to fill it.`,
  }[g.reason] || "No application form was recognised on this page.";
  return show(
    h("h2", {}, `${d.platform} page`),
    note(g.reason === "no_fields" ? "warn" : "bad", why),
    g.reason === "frame" ? h("button", { type: "button", class: "primary", onclick: async () => {
      try { if (await chrome.permissions.request({ origins: [g.origin] })) main(); } catch { /* the user closed Chrome's prompt */ }
    } }, `Allow Smart Apply on ${g.frameHost}`) : null,
    h("details", { class: "muted" }, h("summary", {}, "What JobPilot found"),
      h("p", {}, `Fields on the page: ${g.lightFields ?? 0}; inside page components: ${g.deepFields ?? 0}; components: ${g.shadowHosts ?? 0}; forms: ${g.forms ?? 0}.`)),
    h("div", { class: "row" }, again, h("button", { type: "button", onclick: downloadResume(null, null) }, "Download my resume")));
}

/** Sites whose terms forbid automation: never touched. Copy-ready details and the resume instead. */
async function handoffView(blocked) {
  const r = await send("handoff");
  const rows = r.ok ? r.data.rows : [];
  const copy = (v) => async (e) => {
    try { await navigator.clipboard.writeText(v); e.currentTarget.textContent = "Copied"; } catch { e.currentTarget.textContent = "Copy failed"; }
  };
  show(
    h("h2", {}, `${blocked.name}: apply yourself`),
    note("warn", blocked.why, h("div", {}, "JobPilot does not fill or submit anything here. Use the details below, then record the application in JobPilot.")),
    h("div", { class: "card" },
      h("strong", {}, "Your details (click to copy)"),
      rows.length ? h("ul", { class: "copy" }, rows.map(([k, v]) => h("li", {}, h("span", { class: "muted" }, `${k}: `), h("button", { type: "button", class: "link", onclick: copy(String(v)) }, String(v).slice(0, 60)))))
        : h("p", { class: "muted" }, r.ok ? "Your profile has no details yet." : r.error)),
    h("div", { class: "row" },
      h("button", { type: "button", onclick: downloadResume(null, null) }, "Download my resume"),
      linkTo("Record it in JobPilot", "applied")),
    h("p", { class: "muted" }, "Tip: use the “Clip to JobPilot” bookmark on the job page to add the job to JobPilot first."));
}

/** Other employer sites: Chrome asks the user to allow Smart Apply on that one site. */
function permissionView(req) {
  const msg = h("div");
  const host = req.origin.replace(/^https:\/\//, "").replace(/\/\*$/, "");
  show(
    h("h2", {}, req.known ? `${req.name} application` : "Employer application site"),
    h("p", {}, `Smart Apply can fill this form after you allow it on ${host}. Chrome will ask you to confirm. JobPilot will only run here when you click Fill.`),
    note("warn", "On this site JobPilot fills and checks the form; you submit it on the page yourself."),
    h("button", { type: "button", class: "primary", onclick: async () => {
      let ok = false;
      try { ok = await chrome.permissions.request({ origins: [req.origin] }); } catch (e) { msg.replaceChildren(note("bad", e.message)); return; }
      if (ok) main(); else msg.replaceChildren(note("warn", "Not allowed. Nothing was changed."));
    } }, `Allow Smart Apply on ${host}`),
    msg);
}

function missingCard(missing) {
  if (!missing.length) return null;
  const profile = missing.filter((m) => m.where === "settings/profile");
  const answers = missing.filter((m) => m.where === "settings/answers");
  return note("warn",
    h("strong", {}, "Missing from your JobPilot profile"),
    h("ul", {}, missing.slice(0, 8).map((m) => h("li", {}, m.label))),
    h("div", { class: "row" },
      profile.length ? linkTo("Update profile", "settings?tab=profile") : null,
      answers.length ? linkTo("Add verified answers", "settings?tab=answers") : null));
}

function resumeOptions(resumes) {
  const opts = [];
  for (const r of resumes) {
    if (r.kind === "upload") {
      const f = r.formats?.[0] || "pdf";
      opts.push({ value: `upload:${r.id}:${f}`, label: `${r.name}${r.active ? " (default)" : ""} · uploaded ${f === "docx" ? "Word" : "PDF"}` });
    }
    else for (const f of r.formats) opts.push({ value: `studio:${r.id}:${f}`, label: `${r.name} · Resume Studio ${f.toUpperCase()}` });
  }
  return opts;
}
const parseChoice = (v) => { const [kind, id, format] = String(v || "").split(":"); return kind ? { kind, id: Number(id), format } : null; };

function downloadResume(getChoice, out) {
  return async (e) => {
    const done = busy(e.currentTarget, "Downloading…");
    const r = await send("downloadResume", { resume: getChoice ? getChoice() : null });
    done();
    if (!r.ok) return out?.replaceChildren(note("bad", r.error));
    const bytes = Uint8Array.from(atob(r.data.b64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: r.data.type }));
    const a = h("a", { href: url, download: r.data.name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    out?.replaceChildren(note("ok", `Saved ${r.data.name} to your Downloads. Attach it on the form yourself.`));
  };
}

function formView(d, missing) {
  const { form, match, tabId, resumes = [], session } = d;
  const target = { tabId, frameId: form.frameId };
  let applicationId = match?.application_id ?? session?.applicationId ?? null;
  const submitted = match?.application_status === "SUBMITTED";
  const applyState = match?.apply_state || session?.state || null;

  const header = h("div", { class: "card" },
    h("div", {}, h("span", { class: "badge" }, form.platform), " ", h("strong", {}, match?.title || form.title || "Application form")),
    match?.company ? h("div", { class: "muted" }, [match.company, match.location].filter(Boolean).join(" · ")) : null,
    form.step?.title ? h("div", { class: "muted" }, `Step ${form.step.index ?? "?"}${form.step.total ? ` of ${form.step.total}` : ""}: ${form.step.title}`) : null,
    match?.error ? note("bad", match.error)
      : match?.in_jobpilot
        ? h("div", { class: "muted" }, submitted ? `Applied ${new Date(match.submitted_at).toLocaleDateString()} (recorded in JobPilot). JobPilot will not submit it again.`
          : match.apply_state_label ? `In your JobPilot jobs · ${match.apply_state_label}` : "In your JobPilot jobs. Your application will be tracked.")
        : h("div", { class: "muted" }, "Not in your JobPilot jobs, so it will not be tracked. You can still fill the form."),
    h("div", { class: "muted" }, form.assistedSubmit ? "Smart Apply: fill, review, then submit from the review panel or on the page." : "Smart Apply: fill and review here; you submit on the page."));

  // After a browser restart or a closed tab: the last submission was never confirmed.
  const verify = !submitted && applicationId && ["submission_pending", "submission_uncertain"].includes(applyState)
    ? note("warn", h("strong", {}, "Did your last submission go through?"),
        h("div", {}, "JobPilot could not see a confirmation. Check the employer's page or your email."),
        h("div", { class: "row" },
          h("button", { type: "button", class: "primary", onclick: async () => { await send("confirm", { applicationId, submitted: true, tabId }); main(); } }, "Yes, submitted"),
          h("button", { type: "button", onclick: async () => { await send("confirm", { applicationId, submitted: false, tabId }); main(); } }, "No")))
    : null;

  const opts = resumeOptions(resumes);
  // Shown first: the resume picked here earlier for this page, else the one the user chose for this application in
  // JobPilot. Nothing is preselected otherwise: the user chooses (JobPilot never attaches a default on its own).
  const fromPkg = !session?.resume && session?.packageResumeConfirmed ? session.packageResume : null;
  const pre = session?.resume || fromPkg || null;
  const chosen = pre ? `${pre.kind}:${pre.id}:${pre.format}` : "";
  const select = h("select", { "aria-label": "Resume to attach" },
    h("option", { value: "", disabled: true, selected: !chosen }, "Choose a resume…"),
    opts.map((o) => h("option", { value: o.value, selected: o.value === chosen }, o.label)));
  const choice = () => parseChoice(select.value);
  // Only a resume the user picked here (or saw preselected here and attached) overrides the application's choice.
  let picked = Boolean(session?.resume);
  const origin = h("p", { class: "muted" }, session?.resume ? "Picked here for this page." : fromPkg ? "Chosen for this application in JobPilot."
    : "Not chosen yet. Pick the resume to send with this application.");
  select.addEventListener("change", () => { picked = true; origin.textContent = "Picked here. JobPilot attaches exactly this file."; syncButtons(); });
  const pickedChoice = () => (picked ? choice() : null);

  const overwrite = h("input", { type: "checkbox" });
  const result = h("div");
  const resumeMsg = h("div");
  const fillBtn = h("button", { type: "button", class: "primary", disabled: submitted, onclick: async () => {
    const done = busy(fillBtn, "Filling…");
    const r = await send("fill", { ...target, overwrite: overwrite.checked, resume: pickedChoice(), userJobId: match?.in_jobpilot && !submitted ? match.user_job_id : null });
    done();
    if (!r.ok) return result.replaceChildren(note("bad", r.error));
    const rep = r.data.report || {};
    if (rep.error) return result.replaceChildren(note("bad", rep.error));
    if (r.data.tracking?.application_id) { applicationId = r.data.tracking.application_id; confirmBox.hidden = false; }
    result.replaceChildren(note(rep.needs?.length ? "warn" : "ok",
      h("strong", {}, `${rep.filled.length} filled · ${rep.review.length + (rep.unsure?.length || 0)} to check · ${rep.needs.length} need you · ${rep.kept.length} kept · ${rep.skipped.length} skipped`),
      h("div", {}, "The review panel is open on the page. Check every answer before you submit.")));
  } }, submitted ? "Already applied" : "Fill with JobPilot");

  const attach = (replace) => async (e) => {
    const done = busy(e.currentTarget, "Attaching…");
    // The file shown in the list is the one attached: the user sees and confirms it by clicking Attach.
    const r = await send("attachResume", { ...target, replace, resume: choice() });
    done();
    if (!r.ok) return resumeMsg.replaceChildren(note("bad", r.error));
    const res = r.data || {};
    if (res.ok) return resumeMsg.replaceChildren(note("ok", `Attached and checked on the form: ${res.name} (${Math.round(res.size / 1024)} KB).`, res.note ? h("div", {}, res.note) : null));
    resumeMsg.replaceChildren(note("warn", res.reason || "Could not attach the file.",
      res.needsConfirm ? h("div", { class: "row" }, h("button", { type: "button", onclick: attach(true) }, "Replace")) : null,
      res.manual ? h("div", { class: "row" }, h("button", { type: "button", onclick: downloadResume(choice, resumeMsg) }, "Download it to attach yourself")) : null));
  };
  const attachBtn = h("button", { type: "button", onclick: attach(false) }, form.resumeAttached ? "Replace" : "Attach");
  const dlBtn = h("button", { type: "button", onclick: downloadResume(choice, resumeMsg) }, form.resumeField ? "Download" : "Download resume");
  function syncButtons() { attachBtn.disabled = dlBtn.disabled = !choice(); }
  syncButtons();

  const resumeCard = h("div", { class: "card" },
    h("strong", {}, "Resume"),
    opts.length ? [select, origin] : h("p", { class: "muted" }, "No resume in JobPilot yet. Upload one in Settings or build one in Resume Studio."),
    form.resumeFirst ? h("p", { class: "muted" }, `${form.platform}: attach your resume first. ${form.platform} reads it and may fill some fields; then click Fill.`) : null,
    form.resumeField
      ? h("div", { class: "row" }, attachBtn, dlBtn)
      : h("div", {}, h("p", { class: "muted" }, "No resume field found on this part of the form: download it and attach it yourself if the form asks."), dlBtn),
    form.coverLetterField ? h("p", { class: "muted" }, "This form also takes a cover letter file. Attach it on the page yourself.") : null,
    resumeMsg);

  const ref = h("input", { type: "text", maxlength: "200", placeholder: "Reference ID (optional)", "aria-label": "Reference ID" });
  const confirmMsg = h("div");
  const confirmBtn = (submittedFlag, text, cls) => h("button", { type: "button", class: cls, onclick: async (e) => {
    if (!applicationId) return;
    const done = busy(e.currentTarget, "Saving…");
    const r = await send("confirm", { applicationId, submitted: submittedFlag, referenceId: ref.value.trim(), tabId });
    done();
    if (!r.ok) return confirmMsg.replaceChildren(note("bad", r.error));
    confirmMsg.replaceChildren(note("ok", submittedFlag
      ? (r.data.already_submitted ? "Already recorded as applied. Nothing changed." : "Recorded as applied in JobPilot.")
      : "Recorded as not submitted. You can apply later."));
  } }, text);
  const confirmBox = h("div", { class: "card", hidden: !applicationId || submitted },
    h("strong", {}, "Submitted on the page yourself?"),
    h("p", { class: "muted" }, "JobPilot records a submission when it sees the employer's confirmation. If it could not, tell it here."),
    ref,
    h("div", { class: "row" }, confirmBtn(false, "I didn't submit"), confirmBtn(true, "I submitted it", "primary")),
    confirmMsg);

  show(header, verify, missingCard(missing), resumeCard,
    h("div", { class: "card" },
      fillBtn,
      h("label", { class: "check" }, overwrite, h("span", {}, "Overwrite values already on the form (values you typed after filling are never replaced)")),
      result),
    confirmBox);
}

// ---- settings ----------------------------------------------------------------------------------

async function settingsView() {
  const st = await send("state");
  const base = await send("apiBase");
  const input = h("input", { type: "text", value: st.data?.apiBaseOverride || "", placeholder: base.ok ? base.data.base : "https://…" });
  const msg = h("div");
  show(
    h("h2", {}, "Settings"),
    h("div", { class: "card" },
      h("strong", {}, "JobPilot server"),
      h("p", { class: "muted" }, "Found automatically from the JobPilot web app. Override only for a local development server."),
      input,
      h("div", { class: "row" },
        h("button", { type: "button", onclick: async () => { const r = await send("setApiBase", { url: input.value.trim() || null }); msg.replaceChildren(note(r.ok ? "ok" : "bad", r.ok ? "Saved." : r.error)); } }, "Save"),
        h("button", { type: "button", onclick: async () => { input.value = ""; await send("setApiBase", { url: null }); msg.replaceChildren(note("ok", "Using the automatic address.")); } }, "Automatic")),
      msg),
    st.data?.connected ? h("div", { class: "card" },
      h("strong", {}, "Connection"),
      h("p", { class: "muted" }, `Connected as ${st.data.status?.user_display_name || st.data.info?.user || "you"}. Expires ${st.data.info?.expiresAt ? new Date(st.data.info.expiresAt).toLocaleDateString() : "—"}; renewed automatically while you use it.`),
      h("button", { type: "button", onclick: async () => { await send("disconnect"); main(); } }, "Disconnect this browser")) : null,
    h("button", { type: "button", onclick: main }, "Back"));
}

document.getElementById("settings").addEventListener("click", settingsView);
main();
