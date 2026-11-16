// Any other employer application form, only on sites the user allowed one by one (Chrome asks them). Covers
// employer-hosted systems such as iCIMS, SAP SuccessFactors, Oracle Taleo / Recruiting, Zoho Recruit, Freshteam,
// Darwinbox and SmartRecruiters at the "autofill and review" level (Mode A). Fields are recognised from labels and
// HTML attributes only; JobPilot never submits here.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.adapters.generic) return;
  const { visible } = JP.dom;

  const KNOWN = [
    [/(^|\.)icims\.com$/, "iCIMS"], [/(^|\.)(successfactors\.(com|eu)|sapsf\.(com|eu|cn))$/, "SAP SuccessFactors"],
    [/(^|\.)taleo\.net$/, "Oracle Taleo"], [/(^|\.)oraclecloud\.com$/, "Oracle Recruiting"], [/(^|\.)zohorecruit\.(com|in|eu)$/, "Zoho Recruit"],
    [/(^|\.)freshteam\.com$/, "Freshteam"], [/(^|\.)darwinbox\.(in|com)$/, "Darwinbox"], [/(^|\.)smartrecruiters\.com$/, "SmartRecruiters"],
  ];
  const platformName = (h = location.hostname) => (KNOWN.find(([re]) => re.test(h)) || [null, "Employer site"])[1];

  /** The application form: the visible form (or main region) with the most fillable fields, if it asks for an email or name. */
  function root() {
    const cands = [...document.querySelectorAll("form")].filter(visible);
    if (!cands.length) cands.push(document.querySelector("main") || document.body);
    let best = null; let n = 0;
    for (const f of cands) {
      const fields = [...f.querySelectorAll("input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea")].filter(visible);
      const identity = fields.some((e) => e.type === "email" || /e-?mail|first.?name|full.?name|surname|last.?name/i.test(`${e.name} ${e.id} ${e.getAttribute("autocomplete")} ${e.getAttribute("aria-label")}`) ||
        [...(e.labels || [])].some((l) => /e-?mail|first name|full name|last name/i.test(l.textContent)));
      if (identity && fields.length > n) { best = f; n = fields.length; }
    }
    return n >= 2 ? best : null;
  }

  JP.adapters.generic = {
    generic: true,
    get name() { return platformName(); },
    hosts: [],
    matchesHost: () => true,
    isApplicationPage: () => Boolean(root()),
    root,
    assistedSubmit: false,
    jobTitle: () => document.querySelector("h1")?.textContent?.trim() || null,
    warnings: () => [`${platformName()}: JobPilot recognises fields from their labels only on this site. Check every answer, then submit on the page yourself.`],
    resumeInput: () => {
      const r = root() || document;
      const files = [...r.querySelectorAll("input[type=file]")];
      const named = files.filter((f) => /resume|cv|curriculum/i.test(`${f.name} ${f.id} ${f.getAttribute("aria-label")} ${[...(f.labels || [])].map((l) => l.textContent).join(" ")}`));
      return named.length === 1 ? named[0] : files.length === 1 ? files[0] : null;
    },
    hasResume: () => false,
  };
  JP.platformName = platformName;
})();
