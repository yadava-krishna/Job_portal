// Greenhouse hosted application form (job-boards.greenhouse.io, including the /embed/job_app form that employers
// embed in an iframe). Fields use stable ids; dropdowns are react-select comboboxes (no native <select>).
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.adapters.greenhouse) return;

  const BY_ID = { first_name: "first_name", last_name: "last_name", email: "email", phone: "phone", "candidate-location": "location",
                  "school--0": "school", "degree--0": "degree" };
  const SKIP_ID = {
    preferred_name: "Optional. Fill it only if you go by a different first name.",
    country: "Choose your country yourself (it sets the phone number format).",
  };

  const form = () => document.querySelector("#application-form") || document.getElementById("first_name")?.closest("form") || null;

  JP.adapters.greenhouse = {
    name: "Greenhouse",
    hosts: ["job-boards.greenhouse.io", "boards.greenhouse.io", "job-boards.eu.greenhouse.io", "boards.eu.greenhouse.io"],
    isApplicationPage: () => Boolean(form() && document.getElementById("first_name")),
    root: form,
    jobTitle: () => document.querySelector(".job__title h1, h1.section-header, h1")?.textContent?.trim() || null,
    ignore: (el) => /^iti-/.test(el.id || "") || el.id === "resume_text" || el.id === "cover_letter_text",
    profileKey: (q) => BY_ID[q.els[0].id],
    skip: (q) => SKIP_ID[q.els[0].id] || (/^discipline--/.test(q.els[0].id) ? "Choose your field of study yourself." : null)
      || (/^(start|end)-(month|year)--/.test(q.els[0].id) ? "Dates: fill these yourself." : null)
      || (/--[1-9]$/.test(q.els[0].id) ? "Only your most recent entry is filled. Add others yourself." : null),
    comboValue: (input) => input.closest(".select__control, .select-shell, .select")?.querySelector(".select__single-value, [class*='singleValue']")?.textContent?.trim() || "",
    resumeInput: () => document.querySelector("input[type=file]#resume"),
    hasResume: () => {
      const input = document.querySelector("input[type=file]#resume");
      if (input?.files?.length) return true;
      const group = input?.closest(".file-upload, .field-wrapper, fieldset, div");
      return Boolean(group?.querySelector(".file-upload__filename, [class*='filename'], button[aria-label^='Remove']"));
    },
    afterResumeNote: null,
  };
})();
