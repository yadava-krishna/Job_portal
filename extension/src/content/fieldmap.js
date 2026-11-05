// Field vocabulary shared by all adapters: which profile value a form field asks for, judged from its label.
// Injected into application frames only after the user clicks Fill. No network access, no storage access.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.fieldmap) return;

  // key -> label patterns (tested against the normalised label). Order matters: first match wins.
  const PROFILE_FIELDS = [
    ["first_name", [/^(legal )?first name\b/, /^given name\b/, /^forename\b/]],
    ["last_name", [/^(legal )?last name\b/, /^surname\b/, /^family name\b/]],
    ["full_name", [/^(your )?(full |legal )?name\b(?! of)/, /^candidate name\b/]],
    ["email", [/^(your )?e-?mail( address)?\b/]],
    ["phone", [/^(your )?(phone|mobile|contact|cell)( phone)?( number| no\.?)?\b/]],
    ["linkedin_url", [/linkedin( profile)?( url| link)?\b/]],
    ["github_url", [/^github( profile)?( url| link)?\b/]],
    ["portfolio_url", [/^(portfolio|work samples?)( url| link| website)?\b/]],
    ["website_url", [/^(personal )?(website|web site|blog)( url| link)?\b/, /^other (url|link|website)\b/]],
    ["current_company", [/^current (company|employer|organi[sz]ation)\b/, /^(present|current|most recent) employer\b/]],
    ["current_title", [/^current (job )?(title|designation|role|position)\b/]],
    ["location", [/^(current )?(location|city)\b/, /^where are you (currently )?(based|located)/]],
    ["school", [/^(school|university|college|institution)( name)?\b/]],
    ["degree", [/^(degree|qualification)\b/]],
  ];

  // Never filled automatically, whatever the profile holds.
  const SENSITIVE = /\b(gender|pronoun|sex\b|sexual|orientation|race|racial|ethnic|hispanic|latin[oa]|veteran|disabilit|religio|caste|date of birth|birth ?date|\bage\b|marital|nationality|citizenship number|passport|aadhaar|pan (card|number)|ssn|social security|criminal|convict|salary history)\b/;
  const CONSENT = /\b(i (agree|consent|acknowledge|certify|confirm|understand)|agree to|consent|privacy (policy|notice)|terms (of|and)|gdpr|data (processing|retention)|accurate (and|&) complete|true and correct)\b/;
  const SECRET = /\b(password|passcode|otp|one[- ]time|verification code|captcha|security code|pin\b)/;

  function norm(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[✱*]/g, " ")
      .replace(/\(optional\)|\(required\)/g, " ")
      .replace(/[^a-z0-9+&@./ -]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function profileKeyFor(label) {
    const l = norm(label);
    if (!l) return null;
    for (const [key, patterns] of PROFILE_FIELDS) if (patterns.some((p) => p.test(l))) return key;
    return null;
  }

  function classify(label) {
    const l = norm(label);
    if (SECRET.test(l)) return "secret";
    if (SENSITIVE.test(l)) return "sensitive";
    if (CONSENT.test(l)) return "consent";
    return null;
  }

  /** Option lists that reveal a demographic question even when its label does not. */
  function classifyOptions(options) {
    const o = (options || []).map(norm);
    return o.some((t) => /^(male|female|man|woman|non-binary|transgender|prefer not to (say|disclose|answer))$/.test(t)) ? "sensitive" : null;
  }

  // ---- matching an answer to the options of a select / radio group / combobox ---------------

  const UNIT_DAYS = { day: 1, days: 1, week: 7, weeks: 7, month: 30, months: 30 };

  function quantity(text) {
    // "30 days" -> {n: 30, unit: "days"}, "6.5 years (...)" -> {n: 6.5, unit: "years"}, "9 LPA" -> {n: 9, unit: "lpa"}
    const m = /(\d+(?:\.\d+)?)\s*(days?|weeks?|months?|years?|yrs?|lpa|lakhs?|l\b)?/i.exec(String(text || ""));
    if (!m) return null;
    let unit = (m[2] || "").toLowerCase();
    if (/^yrs?$/.test(unit) || /^years?$/.test(unit)) unit = "years";
    if (/^(lakhs?|l)$/.test(unit)) unit = "lpa";
    if (unit in UNIT_DAYS) return { n: Number(m[1]) * UNIT_DAYS[unit], unit: "days" };
    return { n: Number(m[1]), unit: unit || null };
  }

  function rangeOf(optionText) {
    const t = String(optionText || "").toLowerCase().replace(/[–—]/g, "-").replace(/\s+/g, " ").trim();
    const unitM = /(days?|weeks?|months?|years?|yrs?|lpa|lakhs?)/.exec(t);
    let unit = unitM ? unitM[1] : null;
    let mult = 1;
    if (unit && /^(days?|weeks?|months?)$/.test(unit)) { mult = UNIT_DAYS[unit]; unit = "days"; }
    else if (unit && /^(years?|yrs?)$/.test(unit)) unit = "years";
    else if (unit && /^(lpa|lakhs?)$/.test(unit)) unit = "lpa";
    let m;
    if ((m = /(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)/.exec(t))) return { lo: +m[1] * mult, hi: +m[2] * mult, unit };
    if ((m = /(?:less than|under|below|up to|upto|<|within)\s*(\d+(?:\.\d+)?)/.exec(t))) return { lo: -Infinity, hi: +m[1] * mult, unit };
    const U = "(?:days?|weeks?|months?|years?|yrs?|lpa|lakhs?)?";
    if ((m = new RegExp(`(\\d+(?:\\.\\d+)?)\\s*${U}\\s*(?:\\+|or more|and above|& above|plus|and more|or above)`).exec(t)) ||
        (m = /(?:more than|above|over|>)\s*(\d+(?:\.\d+)?)/.exec(t)))
      return { lo: +m[1] * mult, hi: Infinity, unit };
    if (/\b(immediate|immediately|0 days)\b/.test(t)) return { lo: 0, hi: 0, unit: "days" };
    return null;
  }

  /** Index of the single option matching `answer`, or -1. Exact text first, then yes/no, then numeric ranges. */
  function matchOption(answer, options) {
    const a = norm(answer);
    if (!a || !options.length) return -1;
    const texts = options.map(norm);
    const exact = texts.flatMap((t, i) => (t === a ? [i] : []));
    if (exact.length === 1) return exact[0];
    const yn = /^(yes|no)\b/.exec(a);
    if (yn) {
      const hits = texts.flatMap((t, i) => (new RegExp(`^${yn[1]}\\b`).test(t) ? [i] : []));
      if (hits.length === 1) return hits[0];
      return -1;
    }
    const q = quantity(answer);
    if (q) {
      const hits = options.flatMap((o, i) => {
        const r = rangeOf(o);
        if (!r) return [];
        if (r.unit && q.unit && r.unit !== q.unit) return [];
        return q.n >= r.lo && q.n <= r.hi ? [i] : [];
      });
      if (hits.length === 1) return hits[0];
    }
    return -1;
  }

  JP.fieldmap = { norm, profileKeyFor, classify, classifyOptions, matchOption, quantity, rangeOf };
})();
