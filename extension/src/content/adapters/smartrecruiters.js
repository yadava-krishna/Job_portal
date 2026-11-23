// SmartRecruiters application form ("OneClick" apply: jobs.smartrecruiters.com/oneclick-ui/…, also served from
// www.smartr.me). Runs only on sites the user allowed (optional host permission), at the "autofill and review"
// level: JobPilot fills and checks the form, the user submits it on the page, and JobPilot records the outcome only
// from SmartRecruiters' own confirmation.
//
// Why a dedicated adapter: SmartRecruiters builds its pages from web components (spl-* elements) that keep their
// inputs and labels inside shadow roots, and the application is not necessarily inside a <form> element. The
// generic adapter only reads the light DOM inside <form>s, so it saw no fields and the popup said "No application
// form is visible yet" while the form was on screen. This adapter reads through shadow roots (JP.dom.deepAll) and
// recognises fields by meaning: label text, autocomplete, the input's name, and the Angular form-control name on
// the component that hosts it. Nothing here clicks Submit.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.adapters.smartrecruiters) return;
  const { clean, visible, deepAll, closestDeep, shadowOf } = JP.dom;

  const HOST = /(^|\.)smartrecruiters\.com$|(^|\.)smartr\.me$/;
  // Form-control names used by the OneClick form -> JobPilot profile keys. Matched case-insensitively against the
  // input's own name/id and the formcontrolname / name attributes of the components around it.
  const CONTROL = [
    [/^(first ?name|given ?name)$/, "first_name"], [/^(last ?name|family ?name|surname)$/, "last_name"],
    [/^(confirm(ation)? ?e-?mail|e-?mail ?confirm(ation)?|re ?enter ?e-?mail|e-?mail ?repeat)$/, "email_confirm"],
    [/^e-?mail$/, "email"], [/^(phone ?number|phone|mobile|tel)$/, "phone"],
    [/^(phone ?country(code)?|country ?code|dial ?code|calling ?code)$/, "phone_country_code"],
    [/^(location|city|current ?location)$/, "location"],
    [/^(linked ?in|linkedin ?url|linkedin ?profile)$/, "linkedin_url"], [/^(website|web ?site|personal ?website|portfolio)$/, "website_url"],
  ];
  const tokens = (s) => String(s || "").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase().replace(/[^a-z0-9]+/g, " ")
    .replace(/\b(input|field|control|spl|oc)\b/g, " ").replace(/\s+/g, " ").trim();

  /** Text of a node including its shadow content (labels and file names live inside components). */
  function deepText(node, depth = 0) {
    if (!node || depth > 8) return "";
    let out = "";
    for (const n of node.childNodes) {
      if (n.nodeType === 3) out += n.nodeValue + " ";
      else if (n.nodeType === 1 && !/^(script|style|input|select|textarea|option)$/i.test(n.localName)) {
        const sr = shadowOf(n);
        out += (sr ? deepText(sr, depth + 1) + " " : "") + deepText(n, depth + 1) + " ";
      }
    }
    return clean(out);
  }

  /** The chain of component hosts around an element inside shadow DOM, innermost first. */
  function hosts(el) {
    const out = [];
    let r = el.getRootNode?.();
    while (r && r.host && out.length < 6) { out.push(r.host); r = r.host.getRootNode?.(); }
    return out;
  }

  function fields() {
    return deepAll(document.body, "input:not([type=hidden]),select,textarea").filter((e) => e.type === "file" || visible(e));
  }

  function emailField() {
    return fields().find((e) => e.type === "email" || /e-?mail/i.test(`${e.name} ${e.id} ${e.getAttribute("autocomplete") || ""}`)
      || hosts(e).some((h) => /e-?mail/i.test(`${h.getAttribute("formcontrolname") || ""} ${h.getAttribute("label") || ""}`)));
  }

  /** Label for an input: its own <label> (same shadow root), then the hosting component's label attribute or the
   *  text of the nearest field wrapper around the component. */
  function label(el) {
    const own = el.labels?.[0] ? deepText(el.labels[0]) : "";
    if (own) return own;
    for (const h of hosts(el)) {
      const attr = h.getAttribute("label") || h.getAttribute("aria-label") || h.getAttribute("placeholder");
      if (attr) return clean(attr) + (h.hasAttribute("required") && !/\*\s*$/.test(attr) ? " *" : "");
      const lbl = shadowOf(h)?.querySelector("label, .label, [class*='label']");
      if (lbl && deepText(lbl)) return deepText(lbl);
    }
    return null;
  }

  function controlKey(el) {
    const names = [el.name, el.id, ...hosts(el).flatMap((h) => [h.getAttribute("formcontrolname"), h.getAttribute("name"), h.id])];
    for (const n of names) {
      const t = tokens(n);
      if (!t) continue;
      for (const [re, key] of CONTROL) if (re.test(t)) return key;
    }
    return null;
  }

  function section(el) {
    const box = closestDeep(el, "section, fieldset, [class*='section'], oc-experience, oc-education, oc-screening-questions");
    const head = box && (box.querySelector("h2, h3, legend, [class*='title']") || null);
    return clean(head ? deepText(head) : "").toLowerCase();
  }

  /** Experience / education entries SmartRecruiters shows (it builds them from the attached resume), as text. */
  function entries(kind) {
    const re = kind === "experience" ? /^(work )?experience\b/i : /^education\b/i;
    const box = deepAll(document.body, "section, fieldset, [class*='section']").find((s) => {
      const h = s.querySelector("h2, h3, legend");
      return h && re.test(clean(deepText(h)));
    });
    if (!box) return null;
    const items = [...box.querySelectorAll("li, [class*='entry'], [class*='item'], oc-experience-item, oc-education-item")]
      .filter((n) => visible(n) && !n.querySelector("li")).map((n) => deepText(n)).filter(Boolean);
    return [...new Set(items)].slice(0, 12);
  }

  function resumeInput() {
    const files = fields().filter((e) => e.type === "file");
    const ctx = (f) => `${f.name} ${f.id} ${f.getAttribute("aria-label") || ""} ${label(f) || ""} ${hosts(f).map((h) => `${h.getAttribute("formcontrolname") || ""} ${h.localName}`).join(" ")} ${section(f)}`;
    const named = files.filter((f) => /resume|\bcv\b|curriculum/i.test(ctx(f)) && !/cover/i.test(ctx(f)));
    return named.length === 1 ? named[0] : files.length === 1 ? files[0] : null;
  }

  function coverLetterInput() {
    const files = fields().filter((e) => e.type === "file");
    return files.find((f) => /cover/i.test(`${f.name} ${f.id} ${label(f) || ""} ${section(f)}`)) || null;
  }

  function submitButton() {
    const btns = deepAll(document.body, "button").filter((b) => visible(b) && /^(submit( application)?|send( application)?|apply( now)?)$/i.test(clean(deepText(b))));
    return btns.length === 1 ? btns[0] : null;
  }

  JP.adapters.smartrecruiters = {
    name: "SmartRecruiters",
    hosts: [],
    deep: true,
    matchesHost: (h) => HOST.test(h),
    // The application is open when a visible e-mail field is on the page (read through shadow roots).
    isApplicationPage: () => Boolean(emailField()),
    // The application region (not the site header's search box): the main area around the e-mail field.
    root: () => closestDeep(emailField() || document.body, "main, [role=main]") || document.body,
    ignore: (el) => Boolean(closestDeep(el, "[role=search], header")),
    assistedSubmit: false,
    resumeFirst: true,  // SmartRecruiters reads the attached resume and pre-fills experience and education from it
    jobTitle: () => clean(deepText(document.querySelector("h1, [class*='job-title'], [data-test*='job-title']"))) || null,
    company: () => clean(document.querySelector("[class*='company-name'], [data-test*='company']")?.textContent) || null,
    label,
    profileKey: (q) => {
      const el = q.els[0];
      if (q.kind === "file") return null;
      return controlKey(el);
    },
    isCoverLetter: (q) => /message to the hiring (team|manager)|cover letter|motivation/i.test(q.label || ""),
    warnings: () => {
      const out = ["SmartRecruiters: JobPilot fills and checks this form; you submit it on the page."];
      for (const [kind, name] of [["experience", "Experience"], ["education", "Education"]]) {
        const e = entries(kind);
        if (e == null) continue;  // the form has no such section
        out.push(e.length ? `${name} on the form (${e.length}): ${e.slice(0, 3).map((x) => x.slice(0, 70)).join("; ")}${e.length > 3 ? "; …" : ""}. SmartRecruiters filled these from your resume: check each one.`
          : `${name} is empty on the form. Attach your resume (SmartRecruiters fills it from the file) or add your entries before submitting.`);
      }
      return out;
    },
    entries,
    resumeInput,
    coverLetterInput,
    hasResume: () => {
      const input = resumeInput();
      if (input?.files?.length) return true;
      const box = input && (hosts(input).find((h) => /drop|upload|resume|file/i.test(h.localName + " " + (h.className || ""))) || closestDeep(input, "section, [class*='upload']"));
      return Boolean(box && /\.(pdf|docx?)\b/i.test(deepText(box)));
    },
    submitButton,
    submitErrors: () => deepAll(document.body, "[role=alert], [aria-invalid='true'], [class*='error']:not(input):not(select):not(textarea)")
      .filter(visible).map((e) => (e.matches("input,select,textarea") ? `${label(e) || "A field"} is invalid` : clean(deepText(e)))).filter(Boolean).slice(0, 8),
    confirmation: () => {
      if (emailField()) return null;
      const t = deepText(document.body).slice(0, 8000);
      return /thank you for (applying|your application)|application (has been |was )?(submitted|received|sent)|we('|’)ve received your application/i.test(t)
        ? { signal: "SmartRecruiters: application submitted message" } : null;
    },
    afterResumeNote: "SmartRecruiters reads the resume to fill experience and education. Check those sections after it finishes.",
  };
  JP.srDeepText = deepText;
})();
