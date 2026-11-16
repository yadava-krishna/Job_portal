// Workday-hosted application flow (<tenant>.wd<N>.myworkdayjobs.com, myworkdaysite.com). Multi-step: My Information,
// My Experience, Application Questions, Voluntary Disclosures, Self Identify, Review. The candidate signs in to the
// employer's Workday account themselves; JobPilot never creates accounts or enters passwords.
// Support level: autofill and review per step (Mode A). The user moves between steps and submits with Workday's own
// buttons. Field ids follow Workday's data-automation-id / name conventions; anything else falls back to labels.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.adapters.workday) return;
  const clean = (s) => String(s ?? "").replace(/\s+/g, " ").trim();

  const HOST = /(^|\.)(myworkdayjobs\.com|myworkdaysite\.com|myworkday\.com)$/;
  // data-automation-id / name / id fragments -> profile key
  const BY_AUTOMATION = [
    [/legalName(Section)?[_-]+firstName|firstName$/i, "first_name"],
    [/legalName(Section)?[_-]+lastName|lastName$/i, "last_name"],
    [/addressSection[_-]+addressLine1|addressLine1$/i, "address_line1"],
    [/addressSection[_-]+city|--city$/i, "city"],
    [/addressSection[_-]+postalCode|postalCode$/i, "postal_code"],
    [/^email$|--email$|emailAddress$/i, "email"],
    [/phone-number|phoneNumber$/i, "phone_national"],
    [/linkedin/i, "linkedin_url"],
  ];
  const root = () => document.querySelector("[data-automation-id='applyFlowPage'], [data-automation-id='applyFlow']") ||
    document.querySelector("main [data-automation-id='progressBar']")?.closest("main") || null;
  const ids = (el) => [el.getAttribute("data-automation-id"), el.closest("[data-automation-id^='formField-']")?.getAttribute("data-automation-id"),
                       el.getAttribute("name"), el.id].filter(Boolean);

  JP.adapters.workday = {
    name: "Workday",
    hosts: [],
    matchesHost: (h) => HOST.test(h),
    isApplicationPage: () => Boolean(root()),
    root,
    assistedSubmit: false,
    jobTitle: () => clean(document.querySelector("[data-automation-id='jobPostingHeader'], h2[data-automation-id], h1")?.textContent) || null,
    label: (el) => {
      const ff = el.closest("[data-automation-id^='formField-']");
      const l = ff?.querySelector("label, legend");
      return l ? clean(l.textContent).replace(/\*$/, "") : null;
    },
    profileKey: (q) => {
      if (q.kind === "file" || q.kind === "radio" || q.kind === "checkbox") return undefined;
      for (const id of ids(q.els[0])) for (const [re, key] of BY_AUTOMATION) if (re.test(id)) return key;
      return undefined;
    },
    skip: (q) => {
      const id = ids(q.els[0]).join(" ");
      if (/countryPhoneCode|phone-device-type|deviceType/i.test(id)) return "Choose the phone type and country code yourself.";
      if (/password|createAccount|verifyPassword/i.test(id)) return "Account fields: JobPilot never fills these.";
      return null;
    },
    step: () => {
      const bar = document.querySelector("[data-automation-id='progressBar']");
      if (!bar) return null;
      const steps = [...bar.querySelectorAll("li, [data-automation-id^='progressBar'][data-automation-id$='Step']")];
      const active = bar.querySelector("[data-automation-id='progressBarActiveStep']") || steps.find((s) => s.getAttribute("aria-current") === "step");
      const title = clean(active?.textContent).replace(/^(current step \d+ of \d+|step \d+ of \d+)\s*/i, "") || null;
      return { title, index: active ? Math.max(0, steps.indexOf(active)) + 1 : null, total: steps.length || null, final: /review/i.test(title || "") };
    },
    warnings: () => ["Workday: move between steps and submit with Workday's own buttons. JobPilot fills one step at a time."],
    resumeInput: () => document.querySelector("input[type=file][data-automation-id='file-upload-input-ref']") ||
      ([...document.querySelectorAll("input[type=file]")].length === 1 ? document.querySelector("input[type=file]") : null),
    hasResume: () => Boolean(document.querySelector("[data-automation-id='file-upload-successful'], [data-automation-id='fileName']")),
    submitButton: () => null,  // Mode A only on Workday
    confirmation: () => {
      const t = JP.dom.textOf(document.querySelector("main, body")).slice(0, 5000);
      return !root() && /application (has been )?submitted|thank(s| you) for applying/i.test(t) ? { signal: "Workday: application submitted message" } : null;
    },
  };
})();
