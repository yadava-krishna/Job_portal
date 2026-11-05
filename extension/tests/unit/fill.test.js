import { beforeEach, describe, expect, it } from "vitest";
import { PROFILE, fakeLayout, fixture, guardSubmit, load } from "./helpers.js";

beforeEach(() => fakeLayout());

const labels = (items) => items.map((i) => i.label);
const byLabel = (items, l) => items.find((i) => i.label === l);

describe("field vocabulary", () => {
  it("maps labels to profile values and refuses sensitive, consent and secret questions", () => {
    const { fieldmap: f } = load("<p></p>");
    expect(f.profileKeyFor("First Name*")).toBe("first_name");
    expect(f.profileKeyFor("Full name ✱")).toBe("full_name");
    expect(f.profileKeyFor("Name")).toBe("full_name");
    expect(f.profileKeyFor("Name of your referrer")).toBeNull();
    expect(f.profileKeyFor("LinkedIn Profile:")).toBe("linkedin_url");
    expect(f.profileKeyFor("Current company")).toBe("current_company");
    expect(f.profileKeyFor("Why do you want to join us?")).toBeNull();
    expect(f.classify("Are you Hispanic/Latino?")).toBe("sensitive");
    expect(f.classify("Veteran Status")).toBe("sensitive");
    expect(f.classify("What is your age?")).toBe("sensitive");
    expect(f.classify("I agree to the privacy policy")).toBe("consent");
    expect(f.classify("Enter the verification code")).toBe("secret");
    expect(f.classify("What is your notice period?")).toBeNull();
    expect(f.classifyOptions(["Male", "Female", "Prefer not to disclose"])).toBe("sensitive");
  });

  it("matches answers to options only when exactly one option fits", () => {
    const { fieldmap: f } = load("<p></p>");
    expect(f.matchOption("30 days", ["Less than 15 days", "16 to 30 days", "31 to 60 days", "61 to 90 days", "91 days and above"])).toBe(1);
    expect(f.matchOption("2 months", ["Less than 15 days", "16 to 30 days", "31 to 60 days", "61 to 90 days"])).toBe(2);
    expect(f.matchOption("6.5 years (6 years 6 months), calculated from employment dates", ["0-2 years", "2.1-4 years", "4.1 years and above"])).toBe(2);
    expect(f.matchOption("9 LPA", ["0-2 LPA", "2.1-4 LPA", "4.1-7 LPA", "7.1 LPA and above"])).toBe(3);
    expect(f.matchOption("No", ["Yes", "No"])).toBe(1);
    expect(f.matchOption("Yes", ["Yes, I'm currently based in Bengaluru.", "No, but willing to relocate", "No"])).toBe(0);
    expect(f.matchOption("Yes", ["Yes, based here", "Yes, willing to move"])).toBe(-1);  // ambiguous: never guess
    expect(f.matchOption("30 days", ["Immediately", "1-3 months"])).toBe(1);
    expect(f.matchOption("Indian citizen", ["Yes", "No"])).toBe(-1);
  });
});

describe("Lever form (synthetic copy of the structure)", () => {
  it("fills identity fields and verified answers, flags suggestions, never touches sensitive questions or submits", async () => {
    const JP = load(fixture("synthetic", "lever"));
    const submits = guardSubmit();
    const answers = {
      "Total Years of experience": { answer: "6.5 years (6 years 6 months), calculated from employment dates on the resume", status: "SUGGESTED" },
      "What is your notice period?": { answer: "30 days", status: "VERIFIED" },
      "Expected CTC (LPA)": { answer: "9 LPA", status: "VERIFIED" },
      "Why do you want to join us?": { answer: null, status: "NEEDS_INPUT", reason: "cannot be answered from verified information" },
    };
    const r = await JP.core.fill(JP.adapters.lever, { fields: PROFILE, answers });
    const v = (n) => document.querySelector(`[name="${n}"]`).value;
    expect(v("name")).toBe("Test Candidate");
    expect(v("email")).toBe("test.candidate@example.com");
    expect(v("phone")).toBe("+91 9000000000");
    expect(v("org")).toBe("Example Corp");
    expect(v("urls[LinkedIn]")).toBe(PROFILE.linkedin_url);
    expect(v("urls[GitHub]")).toBe(PROFILE.github_url);
    expect(v("urls[Twitter]")).toBe("");
    expect(document.querySelector('input[value="16 to 30 days"]').checked).toBe(true);
    expect(document.querySelector('[name="cards[c1][field3]"]').selectedOptions[0].text).toBe("5-10 LPA");
    expect([...document.querySelectorAll('[name="cards[c1][field0]"]')].some((e) => e.checked)).toBe(false);
    expect(labels(r.review)).toEqual(["Total Years of experience"]);
    expect(labels(r.needs)).toContain("Why do you want to join us?");
    expect(byLabel(r.skipped, "Please select your gender").reason).toMatch(/never answers/);
    expect(byLabel(r.skipped, "Twitter URL").reason).toMatch(/not in your JobPilot profile/);
    expect(r.files.map((f) => f.label)).toEqual(["Resume/CV"]);
    expect(document.querySelector('[name="pw_honeypot"]').value).toBe("");
    expect(submits).toEqual([]);
  });

  it("keeps values already on the form unless overwrite is chosen, and never refills a field the user changed", async () => {
    const JP = load(fixture("synthetic", "lever"));
    const name = document.querySelector('[name="name"]');
    name.value = "Name Lever Parsed";
    let r = await JP.core.fill(JP.adapters.lever, { fields: PROFILE, answers: {} });
    expect(name.value).toBe("Name Lever Parsed");
    expect(byLabel(r.kept, "Full name")).toMatchObject({ current: "Name Lever Parsed", proposed: "Test Candidate", replaceable: true });

    // The user asks for the JobPilot value for that one field (the panel button).
    expect(await JP.useProposed(byLabel(r.kept, "Full name").ref)).toBe(true);
    expect(name.value).toBe("Test Candidate");

    // The user edits a field JobPilot filled; even "overwrite" does not undo their edit.
    const email = document.querySelector('[name="email"]');
    email.value = "typed.by.user@example.com";
    r = await JP.core.fill(JP.adapters.lever, { fields: PROFILE, answers: {}, overwrite: true });
    expect(email.value).toBe("typed.by.user@example.com");
    expect(byLabel(r.kept, "Email").reason).toMatch(/You changed this/);
    // Unchanged JobPilot values are not filled twice.
    expect(byLabel(r.skipped, "Phone").reason).toMatch(/Already filled by JobPilot/);
  });

  it("overwrite replaces values that were there before JobPilot", async () => {
    const JP = load(fixture("synthetic", "lever"));
    document.querySelector('[name="org"]').value = "Wrong Co (parsed)";
    await JP.core.fill(JP.adapters.lever, { fields: PROFILE, answers: {}, overwrite: true });
    expect(document.querySelector('[name="org"]').value).toBe("Example Corp");
  });

  it("lists missing profile values instead of guessing", async () => {
    const JP = load(fixture("synthetic", "lever"));
    const r = await JP.core.fill(JP.adapters.lever, { fields: { ...PROFILE, current_company: undefined, github_url: undefined }, answers: {} });
    expect(byLabel(r.needs, "Current company").reason).toMatch(/Add your current company/);
    expect(document.querySelector('[name="org"]').value).toBe("");
    expect(byLabel(r.needs, "GitHub URL")).toBeTruthy();
  });
});

describe("Greenhouse form (synthetic copy of the structure)", () => {
  it("fills by id, picks combobox options only on an exact match, skips hidden, disabled, EEO and consent fields", async () => {
    const JP = load(fixture("synthetic", "greenhouse"));
    // Behave like react-select's async location search: suggestions appear after typing.
    const loc = document.getElementById("candidate-location");
    loc.addEventListener("input", () => {
      document.getElementById("loc-list").innerHTML = loc.value ? '<div role="option">Bengaluru, Karnataka, India</div><div role="option">Bengaluru Rural, Karnataka, India</div>' : "";
    });
    const submits = guardSubmit();
    const r = await JP.core.fill(JP.adapters.greenhouse, {
      fields: PROFILE,
      answers: { "What is your notice period?": { answer: "30 days", status: "VERIFIED" },
                 "Which regions can you work in?": { answer: null, status: "NEEDS_INPUT" } },
    });
    const val = (id) => document.getElementById(id).value;
    expect(val("first_name")).toBe("Test");
    expect(val("last_name")).toBe("Candidate");
    expect(val("email")).toBe("test.candidate@example.com");
    expect(val("phone")).toBe("+91 9000000000");
    expect(val("preferred_name")).toBe("");
    expect(val("question_1001")).toBe(PROFILE.linkedin_url);
    expect(val("question_1002")).toBe("30 days");
    expect(val("question_1003")).toBe("https://already.example");  // kept
    expect(val("hidden_q")).toBe("");
    expect(val("disabled_q")).toBe("");
    expect(document.getElementById("consent").checked).toBe(false);
    expect(byLabel(r.filled, "Location (City)").value).toBe("Bengaluru, Karnataka, India");
    expect(byLabel(r.review, "Degree")).toMatchObject({ value: "Bachelor's Degree" });  // B.Com → suggested, review
    expect(byLabel(r.skipped, "Country").reason).toMatch(/phone number format/);
    expect(byLabel(r.skipped, "Gender").reason).toMatch(/never answers/);
    expect(byLabel(r.skipped, "Preferred First Name")).toBeTruthy();
    expect(byLabel(r.skipped, "School").reason).toMatch(/choose it yourself/i);
    expect(byLabel(r.needs, "I agree to the privacy policy") || byLabel(r.skipped, "I agree to the privacy policy")).toBeTruthy();
    expect(labels(r.filled)).not.toContain("Hidden question");
    expect(submits).toEqual([]);
  }, 20000);

  it("accepts a phone number the page reformats, and does not refill it on the next click", async () => {
    const JP = load(fixture("synthetic", "greenhouse"));
    const phone = document.getElementById("phone");
    phone.addEventListener("input", () => { phone.value = phone.value.replace(/^\+91 (\d{5})(\d{5})$/, "+91 $1 $2"); });
    let r = await JP.core.fill(JP.adapters.greenhouse, { fields: PROFILE, answers: {} });
    expect(phone.value).toBe("+91 90000 00000");
    expect(byLabel(r.filled, "Phone")).toBeTruthy();
    r = await JP.core.fill(JP.adapters.greenhouse, { fields: PROFILE, answers: {} });
    expect(byLabel(r.skipped, "Phone").reason).toMatch(/Already filled by JobPilot/);
  }, 60000);

  it("refuses to click anything that could submit", () => {
    const JP = load(fixture("synthetic", "greenhouse"));
    const calls = guardSubmit();
    const btn = document.querySelector("button[type=submit]");
    expect(() => JP.core.safeClick(btn)).toThrow(/refused/);
    const untyped = document.createElement("button");
    document.querySelector("form").append(untyped);
    expect(() => JP.core.safeClick(untyped)).toThrow(/refused/);
    const link = document.createElement("a");
    link.setAttribute("role", "option");
    expect(() => JP.core.safeClick(link)).toThrow(/refused/);
    expect(calls).toEqual([]);
  });
});

describe("Ashby form (synthetic copy of the structure)", () => {
  it("fills system fields, radios and yes/no buttons from answers, and ignores the autofill-from-resume drop zone", async () => {
    const JP = load(fixture("synthetic", "ashby"));
    const submits = guardSubmit();
    const no = document.querySelector("button.no");
    let clicked = null;
    no.addEventListener("click", () => { clicked = "No"; no.setAttribute("aria-pressed", "true"); });
    const r = await JP.core.fill(JP.adapters.ashby, {
      fields: PROFILE,
      answers: {
        "Are you willing to relocate to Bengaluru?": { answer: "Yes", status: "VERIFIED" },
        "Total years of experience": { answer: "6.5 years (6 years 6 months)", status: "SUGGESTED" },
        "Will you require visa sponsorship?": { answer: "No", status: "VERIFIED" },
        "What is your current fixed compensation? (Lakhs per annum)": { answer: null, status: "NEEDS_INPUT" },
      },
    });
    expect(document.getElementById("_systemfield_name").value).toBe("Test Candidate");
    expect(document.getElementById("_systemfield_email").value).toBe("test.candidate@example.com");
    expect(document.getElementById("phone_number").value).toBe("+91 9000000000");
    expect(document.getElementById("q_li").value).toBe(PROFILE.linkedin_url);
    expect(document.getElementById("r0").checked).toBe(true);
    expect(document.getElementById("e2").checked).toBe(true);
    expect(clicked).toBe("No");
    expect(labels(r.review)).toEqual(["Total years of experience"]);
    expect(labels(r.needs)).toEqual(["What is your current fixed compensation? (Lakhs per annum)"]);
    expect(r.files.map((f) => f.label)).toEqual(["Resume"]);  // the drop zone is not a question
    expect(JP.adapters.ashby.resumeInput().id).toBe("_systemfield_resume");
    expect(submits).toEqual([]);
  });
});

describe("recorded live forms (local copies, not committed)", () => {
  const cases = [
    ["greenhouse", "greenhouse", { first_name: "Test", last_name: "Candidate", email: PROFILE.email }],
    ["greenhouse_glean", "greenhouse", { first_name: "Test", email: PROFILE.email }],
    ["lever", "lever", { name: "Test Candidate", email: PROFILE.email, org: "Example Corp" }],
    ["ashby", "ashby", { _systemfield_name: "Test Candidate", _systemfield_email: PROFILE.email }],
  ];
  for (const [file, adapter, expected] of cases) {
    const html = fixture("recorded", file);
    it.skipIf(!html)(`${file}: fills the identity fields and never touches EEO questions or submits`, async () => {
      const JP = load(html);
      const submits = guardSubmit();
      const r = await JP.core.fill(JP.adapters[adapter], { fields: PROFILE, answers: {} });
      for (const [k, v] of Object.entries(expected)) {
        const el = document.getElementById(k) || document.querySelector(`[name="${k}"]`);
        expect(el?.value, k).toBe(v);
      }
      const sensitive = [...r.filled, ...r.review].filter((i) => /gender|race|ethnic|hispanic|veteran|disab/i.test(i.label));
      expect(sensitive).toEqual([]);
      expect(submits).toEqual([]);
    }, 30000);
  }
});
