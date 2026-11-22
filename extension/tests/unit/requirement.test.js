// What the employer's form says about each question (required / optional / unknown), date conversion that never guesses,
// the Greenhouse "Enter manually" cover letter, and recovering from a refused submission without losing anything.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PROFILE, fakeLayout, guardSubmit, load } from "./helpers.js";

beforeEach(() => fakeLayout());
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

describe("required, optional or unknown", () => {
  it("uses only what the page says: the required attribute, aria-required, a * or (required) marker, or (optional)", () => {
    const JP = load(`<main><form>
      <label for="e">Email</label><input id="e" type="email" required>
      <label for="a">Portfolio</label><input id="a" aria-required="true">
      <label for="b">Why us? *</label><textarea id="b"></textarea>
      <label for="c">Salary expectations (required)</label><input id="c">
      <label for="d">Pronouns (optional)</label><input id="d">
      <label for="f">Anything else?</label><textarea id="f"></textarea>
    </form></main>`);
    JP.allowGeneric = true;
    const qs = Object.fromEntries(JP.core.scan(JP.core.adapterHere()).map((q) => [q.label, q.requirement]));
    expect(qs).toEqual({ Email: "required", Portfolio: "required", "Why us?": "required", "Salary expectations": "required",
                         Pronouns: "optional", "Anything else?": "unknown" });
    const detected = JP.detect();
    expect(detected.requirements["Why us?"]).toBe("required");
    expect(detected.requirements["Anything else?"]).toBeUndefined();  // unknown is not reported as optional
  });
});

describe("dates", () => {
  it("converts only dates that can mean one day, and never guesses day/month order", () => {
    const JP = load("<main><form></form></main>");
    const iso = JP.filler.isoDate;
    expect(iso("2026-12-01")).toBe("2026-12-01");
    expect(iso("2026/3/5")).toBe("2026-03-05");
    expect(iso("5 March 2026")).toBe("2026-03-05");
    expect(iso("March 5th, 2026")).toBe("2026-03-05");
    expect(iso("25-12-2026")).toBe("2026-12-25");
    expect(iso("12/25/2026")).toBe("2026-12-25");
    expect(iso("07/07/2026")).toBe("2026-07-07");
    for (const bad of ["03/04/2026", "Immediately", "2 weeks", "31 Feb 2026", "2026-13-01", "", null]) expect(iso(bad)).toBeNull();
  });

  it("fills a converted date as a suggestion to check, and asks for an ambiguous one", async () => {
    const JP = load(`<main><form><label for="e">Email</label><input id="e" type="email">
      <label for="s">Earliest start date</label><input id="s" type="date"><label for="j">Joining date</label><input id="j" type="date"></form></main>`);
    JP.allowGeneric = true;
    const r = await JP.fill({ fields: PROFILE, answers: {
      "Earliest start date": { question: "Earliest start date", answer: "5 January 2027", status: "VERIFIED", source: "memory" },
      "Joining date": { question: "Joining date", answer: "03/04/2027", status: "VERIFIED", source: "memory" } } });
    expect(document.getElementById("s").value).toBe("2027-01-05");
    expect(r.review.find((x) => x.label === "Earliest start date")).toBeTruthy();
    expect(document.getElementById("j").value).toBe("");
    expect(r.needs.find((x) => x.label === "Joining date").reason).toMatch(/day and month could be either way round/);
  });
});

describe("Greenhouse cover letter typed in", () => {
  it("puts the prepared cover letter in the 'Enter manually' box as a suggestion, and leaves the resume text box alone", async () => {
    const JP = load(`<main><form id="application-form">
      <label for="first_name">First Name</label><input id="first_name">
      <label for="email">Email</label><input id="email" type="email">
      <input type="file" id="resume"><textarea id="resume_text"></textarea>
      <input type="file" id="cover_letter"><textarea id="cover_letter_text"></textarea>
      <button type="submit">Submit application</button></form></main>`);
    const submits = guardSubmit();
    const r = await JP.core.fill(JP.adapters.greenhouse, { fields: PROFILE, answers: {}, coverLetter: "Dear team, ..." });
    expect(document.getElementById("cover_letter_text").value).toBe("Dear team, ...");
    expect(r.review.find((x) => x.label === "Cover letter")).toMatchObject({ source: "cover letter" });
    expect(document.getElementById("resume_text").value).toBe("");
    expect(submits).toEqual([]);
  });
});

describe("a refused submission", () => {
  it("lists each field the site flagged, can bring it into view, and keeps every value", async () => {
    const JP = load(`<main><form><label for="e">Email</label><input id="e" type="email" value="t@example.com">
      <label for="p">Phone</label><input id="p" aria-invalid="true" aria-describedby="pe"><div id="pe" class="error-message">Enter a valid phone number</div>
      </form></main>`);
    JP.allowGeneric = true;
    const a = JP.core.adapterHere();
    const fields = JP.submit.invalidFields(a);
    expect(fields).toEqual([{ ref: expect.any(String), label: "Phone", message: expect.stringMatching(/valid phone/) }]);
    const phone = document.getElementById("p");
    phone.focus = vi.fn();
    expect(JP.submit.focusField(fields[0].ref)).toBe(true);
    expect(phone.focus).toHaveBeenCalled();
    expect(document.getElementById("e").value).toBe("t@example.com");
    const o = await JP.submit.outcome(a, { timeoutMs: 2500, step: 100 });
    expect(o).toMatchObject({ outcome: "errors", fields: [{ label: "Phone" }] });
    await wait(0);
  }, 10000);
});
