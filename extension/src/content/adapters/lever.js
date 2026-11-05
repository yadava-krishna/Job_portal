// Lever hosted application form (jobs.lever.co/<company>/<id>/apply). Plain HTML form with stable names.
// Lever reads an attached resume and may fill name, email, phone and company itself, so attach the resume first.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.adapters.lever) return;
  const clean = (s) => String(s ?? "").replace(/\s+/g, " ").replace(/✱/g, "").trim();

  const BY_NAME = { name: "full_name", email: "email", phone: "phone", location: "location", org: "current_company",
                    "urls[LinkedIn]": "linkedin_url", "urls[GitHub]": "github_url", "urls[Portfolio]": "portfolio_url" };
  const form = () => document.querySelector("#application-form, form.application-form") ||
    document.querySelector("input[name=email]")?.closest("form") || null;

  function questionLabel(el) {
    const q = el.closest(".application-question") || el.closest("li");
    const lab = q?.querySelector(".application-label .text, .application-label");
    if (!lab) return null;
    const c = lab.cloneNode(true);
    c.querySelectorAll(".required, input, button").forEach((n) => n.remove());
    return clean(c.textContent);
  }

  JP.adapters.lever = {
    name: "Lever",
    hosts: ["jobs.lever.co", "jobs.eu.lever.co"],
    isApplicationPage: () => Boolean(form() && document.querySelector("input[name=email]")),
    root: form,
    resumeFirst: true,
    jobTitle: () => document.querySelector(".posting-header h2, .posting-headline h2, h2")?.textContent?.trim() || null,
    ignore: (el) => ["selectedLocation", "resumeStorageId", "linkedInData", "accountId", "origin", "referer", "socialReferralKey",
                     "socialSource", "source", "timezone"].includes(el.name),
    label: (el) => (el.type === "radio" || el.type === "checkbox" ? null : questionLabel(el)),
    groupLabel: (el) => questionLabel(el),
    profileKey: (q) => BY_NAME[q.els[0].name] ?? (/^urls\[Other/.test(q.els[0].name) ? "website_url" : undefined),
    skip: (q) => (/^urls\[(Twitter|Naukri|Dribbble|Behance)/i.test(q.els[0].name) ? "This link is not in your JobPilot profile. Add it yourself if you want to." : null),
    resumeInput: () => document.querySelector("input[type=file]#resume-upload-input, input[type=file][name=resume]"),
    hasResume: () => {
      const input = document.querySelector("input[type=file]#resume-upload-input, input[type=file][name=resume]");
      if (input?.files?.length) return true;
      const ok = document.querySelector(".resume-upload-success, .resume-upload-filename, .filename");
      return Boolean(ok && ok.textContent.trim() && getComputedStyle(ok).display !== "none");
    },
    afterResumeNote: "Lever reads your resume and may fill some fields itself. Now click Fill. Values already on the form are kept unless you choose to overwrite them.",
  };
})();
