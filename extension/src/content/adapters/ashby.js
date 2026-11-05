// Ashby hosted application form (jobs.ashbyhq.com/<company>/<id>/application). React app; every question sits in a
// [data-field-path] entry with a title. The separate "Autofill from resume" drop zone is never used: JobPilot
// attaches the resume only to the Resume question itself.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.adapters.ashby) return;
  const clean = (s) => String(s ?? "").replace(/\s+/g, " ").trim();

  const BY_PATH = { _systemfield_name: "full_name", _systemfield_email: "email", _systemfield_phone: "phone", _systemfield_location: "location" };
  const root = () => document.querySelector(".ashby-application-form-container") ||
    document.getElementById("_systemfield_name")?.closest("form, [class*='application-form']") || null;
  const entry = (el) => el.closest("[data-field-path]");
  const title = (el) => clean(entry(el)?.querySelector(".ashby-application-form-question-title, label")?.textContent).replace(/\*$/, "").trim() || null;

  JP.adapters.ashby = {
    name: "Ashby",
    hosts: ["jobs.ashbyhq.com"],
    isApplicationPage: () => Boolean(root() && document.getElementById("_systemfield_email")),
    root,
    jobTitle: () => document.querySelector("h1")?.textContent?.trim() || null,
    // The autofill drop zone (and anything else outside a question entry) is not part of the application.
    ignore: (el) => !entry(el),
    label: (el) => (el.type === "radio" || el.type === "checkbox" ? null : title(el)),
    groupLabel: (el) => title(el),
    profileKey: (q) => BY_PATH[entry(q.els[0])?.getAttribute("data-field-path")],
    extraQuestions: (r) => {
      // Yes/No questions are two type="button" buttons, not inputs.
      const out = [];
      for (const e of r.querySelectorAll("[data-field-path]")) {
        if (e.querySelector("input:not([type=hidden]),select,textarea")) continue;
        const btns = [...e.querySelectorAll("button[type=button]")].filter((b) => /^(yes|no)$/i.test(clean(b.textContent)));
        if (btns.length === 2 && JP.core.visible(btns[0])) {
          out.push({ kind: "buttons", els: btns, label: title(btns[0]) || "", options: btns.map((b) => clean(b.textContent)), required: false });
        }
      }
      return out;
    },
    resumeInput: () => document.querySelector("input[type=file]#_systemfield_resume"),
    hasResume: () => {
      const input = document.querySelector("input[type=file]#_systemfield_resume");
      if (input?.files?.length) return true;
      const e = input && entry(input);
      return Boolean(e && /\.(pdf|docx?)\b/i.test(e.textContent || ""));
    },
    afterResumeNote: null,
  };
})();
