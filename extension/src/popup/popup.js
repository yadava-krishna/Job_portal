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
function show(...nodes) { app.replaceChildren(...nodes); }
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
  if (!d.supported) {
    return show(
      h("h2", {}, "Not an application page"),
      h("p", {}, "Fill with JobPilot works on Greenhouse, Lever and Ashby application forms."),
      h("p", { class: "muted" }, "If the job is on an employer's own careers site, open it from JobPilot: for Greenhouse jobs JobPilot offers the Greenhouse application form when one exists."),
      missingCard(missing));
  }
  if (!d.form) {
    return show(h("h2", {}, `${d.platform} page`), note("warn", "No application form is visible yet. Click Apply on the page, then open JobPilot again."));
  }
  formView(d, missing);
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

function formView(d, missing) {
  const { form, match, tabId } = d;
  const target = { tabId, frameId: form.frameId };
  let applicationId = match?.application_id ?? null;
  const submitted = match?.application_status === "SUBMITTED";

  const header = h("div", { class: "card" },
    h("div", {}, h("span", { class: "badge" }, form.platform), " ", h("strong", {}, match?.title || form.title || "Application form")),
    match?.company ? h("div", { class: "muted" }, match.company) : null,
    match?.error ? note("bad", match.error)
      : match?.in_jobpilot
        ? h("div", { class: "muted" }, submitted ? `Applied ${new Date(match.submitted_at).toLocaleDateString()} (recorded in JobPilot)` : "In your JobPilot jobs. Your application will be tracked.")
        : h("div", { class: "muted" }, "Not in your JobPilot jobs, so it will not be tracked. You can still fill the form."));

  const overwrite = h("input", { type: "checkbox" });
  const result = h("div");
  const resumeMsg = h("div");
  const fillBtn = h("button", { type: "button", class: "primary", onclick: async () => {
    const done = busy(fillBtn, "Filling…");
    const r = await send("fill", { ...target, overwrite: overwrite.checked, userJobId: match?.in_jobpilot && !submitted ? match.user_job_id : null });
    done();
    if (!r.ok) return result.replaceChildren(note("bad", r.error));
    const rep = r.data.report || {};
    if (rep.error) return result.replaceChildren(note("bad", rep.error));
    if (r.data.tracking?.application_id) { applicationId = r.data.tracking.application_id; confirmBox.hidden = false; }
    result.replaceChildren(note(rep.needs?.length ? "warn" : "ok",
      h("strong", {}, `${rep.filled.length} filled · ${rep.review.length} to review · ${rep.needs.length} need you · ${rep.kept.length} kept · ${rep.skipped.length} skipped`),
      h("div", {}, "The full list is on the page. Check every answer before you submit.")));
  } }, "Fill with JobPilot");

  const attach = (replace) => async (e) => {
    const done = busy(e.currentTarget, "Attaching…");
    const r = await send("attachResume", { ...target, replace });
    done();
    if (!r.ok) return resumeMsg.replaceChildren(note("bad", r.error));
    const res = r.data || {};
    if (res.ok) return resumeMsg.replaceChildren(note("ok", `Attached ${res.name}.`, res.note ? h("div", {}, res.note) : null));
    resumeMsg.replaceChildren(note("warn", res.reason || "Could not attach the file.",
      res.needsConfirm ? h("div", { class: "row" }, h("button", { type: "button", onclick: attach(true) }, "Replace")) : null));
  };
  const download = async (e) => {
    const done = busy(e.currentTarget, "Downloading…");
    const r = await send("downloadResume");
    done();
    if (!r.ok) return resumeMsg.replaceChildren(note("bad", r.error));
    const bytes = Uint8Array.from(atob(r.data.b64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: r.data.type }));
    const a = h("a", { href: url, download: r.data.name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    resumeMsg.replaceChildren(note("ok", "Saved to your Downloads. Attach it on the form yourself."));
  };

  const resumeCard = h("div", { class: "card" },
    h("strong", {}, "Resume"),
    form.resumeFirst ? h("p", { class: "muted" }, "Lever: attach your resume first. Lever reads it and may fill some fields; then click Fill.") : null,
    form.resumeField
      ? h("div", { class: "row" }, h("button", { type: "button", onclick: attach(false) }, form.resumeAttached ? "Replace with my resume" : "Attach my resume"),
          h("button", { type: "button", onclick: download }, "Download"))
      : h("div", {}, h("p", { class: "muted" }, "No resume field found on this page."), h("button", { type: "button", onclick: download }, "Download resume")),
    resumeMsg);

  const ref = h("input", { type: "text", maxlength: "200", placeholder: "Reference ID (optional)", "aria-label": "Reference ID" });
  const confirmMsg = h("div");
  const confirmBtn = (submittedFlag, text, cls) => h("button", { type: "button", class: cls, onclick: async (e) => {
    if (!applicationId) return;
    const done = busy(e.currentTarget, "Saving…");
    const r = await send("confirm", { applicationId, submitted: submittedFlag, referenceId: ref.value.trim() });
    done();
    if (!r.ok) return confirmMsg.replaceChildren(note("bad", r.error));
    confirmMsg.replaceChildren(note("ok", submittedFlag
      ? (r.data.already_submitted ? "Already recorded as applied. Nothing changed." : "Recorded as applied in JobPilot.")
      : "Recorded as not submitted. You can apply later."));
  } }, text);
  const confirmBox = h("div", { class: "card", hidden: !applicationId || submitted },
    h("strong", {}, "After you submit on this page"),
    h("p", { class: "muted" }, "Only you can say the application was sent. Filling the form does not count as applying."),
    ref,
    h("div", { class: "row" }, confirmBtn(false, "I didn't submit"), confirmBtn(true, "I submitted it", "primary")),
    confirmMsg);

  show(header, missingCard(missing), resumeCard,
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
