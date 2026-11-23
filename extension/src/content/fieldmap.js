// Field vocabulary and the deterministic field classifier shared by all adapters (no AI, no network, no storage).
//
// A field is classified from several signals: its label, the HTML autocomplete token, its name/id, placeholder and
// input type. Each signal proposes a profile key with a confidence; agreeing signals raise it, disagreeing ones lower
// it. Only fields at or above FILL_THRESHOLD are filled; lower-confidence guesses are shown for review, never filled.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.fieldmap) return;

  // key -> label patterns (tested against the normalised label). Order matters: first match wins.
  const PROFILE_FIELDS = [
    ["first_name", [/^(legal )?first name\b/, /^given name\b/, /^forename\b/]],
    ["last_name", [/^(legal )?last name\b/, /^surname\b/, /^family name\b/]],
    ["full_name", [/^(your )?(full |legal )?name\b(?! of)/, /^candidate name\b/]],
    ["email_confirm", [/^(confirm|re-?enter|repeat|retype|verify) (your )?e-?mail( address)?\b/, /^e-?mail( address)? (confirmation|again)\b/]],
    ["email", [/^(your )?e-?mail( address)?\b/]],
    ["phone_country_code", [/^(phone |mobile )?(country|dial(l)?ing|isd) code\b/]],
    ["phone", [/^(your )?(phone|mobile|contact|cell)( phone)?( number| no\.?)?\b/]],
    ["linkedin_url", [/linkedin( profile)?( url| link)?\b/]],
    ["github_url", [/^github( profile)?( url| link)?\b/]],
    ["portfolio_url", [/^(portfolio|work samples?)( url| link| website)?\b/]],
    ["website_url", [/^(personal )?(website|web site|blog)( url| link)?\b/, /^other (url|link|website)\b/]],
    ["current_company", [/^current (company|employer|organi[sz]ation)\b/, /^(present|current|most recent) employer\b/]],
    ["current_title", [/^current (job )?(title|designation|role|position)\b/]],
    ["city", [/^(current )?(town|city)( \/ town)?( of residence)?$/]],
    ["location", [/^(current )?(location|city)\b/, /^where are you (currently )?(based|located)/]],
    ["address_line1", [/^(street |postal |residential |home |current )?address( line 1| 1)?$/, /^street( address)?$/]],
    ["state", [/^(state|province|region)( \/ province| \/ region| of residence)?$/]],
    ["postal_code", [/^(postal|zip|post|pin) ?code$/, /^(pincode|zip|postcode)$/]],
    ["country", [/^(current )?country( of residence| \/ region)?$/]],
    ["graduation_year", [/^(graduation|passing|completion|passed out) year\b/, /^year of (graduation|passing|completion)\b/]],
    ["school", [/^(school|university|college|institution)( name)?\b/]],
    ["degree", [/^(degree|qualification)\b/]],
  ];

  // HTML autocomplete tokens (https://html.spec.whatwg.org/#autofill) -> profile key. Very reliable when present.
  const AUTOCOMPLETE = {
    "given-name": "first_name", "family-name": "last_name", name: "full_name", email: "email", tel: "phone",
    "tel-national": "phone_national", "tel-country-code": "phone_country_code", "address-line1": "address_line1",
    "street-address": "address_line1", "address-level2": "city", "address-level1": "state", "postal-code": "postal_code",
    "country-name": "country", country: "country", organization: "current_company", "organization-title": "current_title",
  };

  // name / id tokens -> profile key (after removing separators: "first_name", "firstName", "fname" -> "firstname").
  const NAME_TOKENS = [
    ["first_name", /^(first ?name|fname|given ?name|forename|legalname ?first ?name|name ?first)$/],
    ["last_name", /^(last ?name|lname|surname|family ?name|legalname ?last ?name|name ?last)$/],
    ["full_name", /^(full ?name|candidate ?name|your ?name)$/],
    ["email", /^(e ?mail|email ?address|candidate ?email)$/],
    ["phone", /^(phone|phone ?number|mobile|mobile ?number|cell|telephone|contact ?number)$/],
    ["linkedin_url", /linked ?in/],
    ["github_url", /^git ?hub/],
    ["portfolio_url", /^portfolio/],
    ["city", /^(city|town)$/],
    ["postal_code", /^(zip|zip ?code|postal ?code|postcode|pin ?code|pincode)$/],
    ["address_line1", /^(address|address ?line ?1|address1|street)$/],
    ["state", /^(state|province|region)$/],
    ["country", /^(country|country ?name)$/],
  ];

  const FILL_THRESHOLD = 0.75;

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
    // A dial code ("+91") against country options ("India (+91)", "+91 India"): the one option carrying that code.
    const dial = /^\+\d{1,4}$/.exec(String(answer).trim());
    if (dial) {
      const code = dial[0].replace("+", "\\+");
      const hits = options.flatMap((o, i) => (new RegExp(`(^|[\\s(])${code}($|[\\s)])`).test(String(o)) ? [i] : []));
      return hits.length === 1 ? hits[0] : -1;
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

  function tokenKey(raw) {
    const t = String(raw || "").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()
      .replace(/\b(input|field|txt|text|fld|candidate|applicant|question)\b/g, " ").replace(/\s+/g, " ").trim();
    if (!t) return null;
    for (const [key, re] of NAME_TOKENS) if (re.test(t)) return key;
    return null;
  }

  /**
   * Classify one field from all its signals.
   * signals = {label, autocomplete, name, id, placeholder, type}
   * Returns {key, confidence (0..1), via: [signal names]} or null. Sensitive/consent/secret fields return
   * {never: "sensitive"|"consent"|"secret"} and are never filled whatever the other signals say.
   */
  function classifyField(signals = {}) {
    for (const text of [signals.label, signals.placeholder]) {
      const never = classify(text);
      if (never) return { never, key: null, confidence: 1, via: ["label"] };
    }
    const votes = [];
    const ac = String(signals.autocomplete || "").toLowerCase().split(/\s+/).filter((t) => !/^(section-|shipping|billing|home|work|mobile|on|off)/.test(t)).pop();
    if (ac && AUTOCOMPLETE[ac]) votes.push([AUTOCOMPLETE[ac], 0.95, "autocomplete"]);
    const byLabel = profileKeyFor(signals.label);
    if (byLabel) votes.push([byLabel, 0.9, "label"]);
    for (const [sig, w] of [["name", 0.7], ["id", 0.65]]) {
      const k = tokenKey(signals[sig]);
      if (k) votes.push([k, w, sig]);
    }
    if (!signals.label) {
      const k = profileKeyFor(signals.placeholder);
      if (k) votes.push([k, 0.6, "placeholder"]);
    }
    const type = String(signals.type || "").toLowerCase();
    if (type === "email") votes.push(["email", 0.8, "type"]);
    if (type === "tel" && !votes.some(([k]) => k === "phone_country_code" || k === "phone_national")) votes.push(["phone", 0.7, "type"]);
    if (!votes.length) return null;
    const byKey = new Map();
    for (const [k, w, via] of votes) {
      const cur = byKey.get(k) || { key: k, confidence: 0, via: [] };
      cur.confidence = cur.confidence ? Math.min(0.99, Math.max(cur.confidence, w) + 0.05) : w;
      cur.via.push(via);
      byKey.set(k, cur);
    }
    const ranked = [...byKey.values()].sort((a, b) => b.confidence - a.confidence);
    const best = { ...ranked[0] };
    // A first/last/full name disagreement is common ("name" attribute on a first-name box): not a real conflict
    // when the label is explicit. Any other disagreement between strong signals lowers confidence below the bar.
    const rival = ranked[1];
    if (rival && rival.confidence >= 0.6 && !(best.via.includes("label") && /name$/.test(best.key) && /name$/.test(rival.key))) {
      best.confidence = Math.min(best.confidence, 0.5);
      best.conflict = rival.key;
    }
    return best;
  }

  JP.fieldmap = { norm, profileKeyFor, classify, classifyOptions, classifyField, tokenKey, matchOption, quantity, rangeOf,
                  FILL_THRESHOLD };
})();
