// "Clip to JobPilot" bookmarklet source: plain ES5, imported with ?raw so the
// build never transforms it. Evaluated as: (<this function>)(portalUrl)
// Runs only when the user clicks it, on the single page they are viewing.
function (portal) {
  var d = document;
  var text = function (sel) {
    var e = d.querySelector(sel);
    return e ? ((e.innerText || e.textContent || "")).replace(/\s+\n/g, "\n").trim() : "";
  };
  var first = function (sels) {
    for (var i = 0; i < sels.length; i++) {
      var v = text(sels[i]);
      if (v) return v;
    }
    return "";
  };
  var job = { url: location.href, title: "", company: "", location: "", description: "", posted_date: "", posted_date_source: "user", salary: "", experience: "" };
  var host = location.hostname;
  var params = new URLSearchParams(location.search);

  // 1. Structured data (schema.org JobPosting) published by the page itself.
  var lds = d.querySelectorAll('script[type="application/ld+json"]');
  for (var i = 0; i < lds.length; i++) {
    try {
      var data = JSON.parse(lds[i].textContent || "null");
      var items = [].concat((data && data["@graph"]) || data || []);
      for (var k = 0; k < items.length; k++) {
        var x = items[k];
        if (!x || x["@type"] !== "JobPosting") continue;
        job.title = job.title || x.title || "";
        job.company = job.company || (x.hiringOrganization && x.hiringOrganization.name) || "";
        var loc = [].concat(x.jobLocation || [])[0];
        if (loc && loc.address && !job.location) job.location = [loc.address.addressLocality, loc.address.addressRegion].filter(Boolean).join(", ");
        if (x.description && !job.description) job.description = new DOMParser().parseFromString(String(x.description), "text/html").body.textContent || "";
        if (x.datePosted) { job.posted_date = String(x.datePosted).slice(0, 10); job.posted_date_source = "page"; }
      }
    } catch (e) { /* ignore malformed JSON-LD */ }
  }

  // 2. Platform-specific page elements (selectors change over time; the user reviews everything).
  var postedText = "";
  if (/linkedin\.com$/.test(host) || /\.linkedin\.com$/.test(host)) {
    var id = params.get("currentJobId") || (location.pathname.match(/jobs\/view\/(?:[^/]*-)?(\d{6,})/) || [])[1];
    if (id) job.url = "https://www.linkedin.com/jobs/view/" + id + "/";
    job.title = first([".job-details-jobs-unified-top-card__job-title h1", ".job-details-jobs-unified-top-card__job-title", ".jobs-unified-top-card__job-title", ".top-card-layout__title", "h1"]) || job.title;
    job.company = first([".job-details-jobs-unified-top-card__company-name a", ".job-details-jobs-unified-top-card__company-name", ".jobs-unified-top-card__company-name", ".topcard__org-name-link"]) || job.company;
    var meta = first([".job-details-jobs-unified-top-card__primary-description-container", ".job-details-jobs-unified-top-card__tertiary-description-container", ".jobs-unified-top-card__primary-description", ".topcard__flavor-row"]);
    if (meta) {
      var parts = meta.split(/·|\n/).map(function (s) { return s.trim(); }).filter(Boolean);
      if (!job.location && parts[0] && !/ago|applicant/i.test(parts[0])) job.location = parts[0];
      postedText = parts.filter(function (s) { return /\bago\b|just now|today/i.test(s); })[0] || "";
    }
    job.description = first(["#job-details", ".jobs-description__content", ".jobs-box__html-content", ".description__text"]) || job.description;
  } else if (/indeed\./.test(host)) {
    var jk = params.get("vjk") || params.get("jk");
    if (jk && /^[0-9a-f]{16}$/i.test(jk)) job.url = location.origin + "/viewjob?jk=" + jk.toLowerCase();
    job.title = (first(['[data-testid="jobsearch-JobInfoHeader-title"]', "h1.jobsearch-JobInfoHeader-title", "h1"]) || job.title).replace(/\s*-\s*job post\s*$/i, "");
    job.company = first(['[data-testid="inlineHeader-companyName"]', '[data-company-name="true"]', ".jobsearch-CompanyInfoContainer a"]) || job.company;
    job.location = first(['[data-testid="inlineHeader-companyLocation"]', '[data-testid="job-location"]', "#jobLocationText"]) || job.location;
    job.salary = first(["#salaryInfoAndJobType", '[data-testid="jobsearch-OtherJobDetailsContainer"]']);
    job.description = first(["#jobDescriptionText", ".jobsearch-jobDescriptionText"]) || job.description;
  } else if (/naukri\.com$/.test(host)) {
    job.title = first(['h1[class*="jd-header-title"]', "h1"]) || job.title;
    job.company = first(['[class*="jd-header-comp-name"] a', '[class*="jd-header-comp-name"]']) || job.company;
    job.location = first(['[class*="jhc__location"]', '[class*="location"] a']) || job.location;
    job.experience = first(['[class*="jhc__exp"]', '[class*="exp"] span']);
    job.salary = first(['[class*="jhc__salary"]', '[class*="salary"] span']);
    job.description = first(['[class*="job-desc-container"]', '[class*="dang-inner-html"]', 'section[class*="job-desc"]']) || job.description;
    var stats = d.querySelectorAll('[class*="jhc__stat"]');
    for (var s = 0; s < stats.length; s++) {
      var t = ((stats[s]).innerText || stats[s].textContent || "").replace(/^\s*posted\s*:?\s*/i, "");
      if (/ago|today|just now/i.test(t)) { postedText = t.trim(); break; }
    }
  }
  if (postedText && !job.posted_date) { job.posted_date = postedText; job.posted_date_source = "page"; }

  // 3. Fallback: whatever the user selected on the page.
  var sel = String(window.getSelection ? window.getSelection() : "").trim();
  if (sel.length > 200 && sel.length > job.description.length / 2) job.description = sel;
  if (!job.title) job.title = (d.title || "").split(/[|\-–]/)[0].trim();
  job.description = job.description.slice(0, 30000);

  var json = JSON.stringify(job);
  var b64 = btoa(unescape(encodeURIComponent(json))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  var w = window.open(portal + "#/clip?d=" + b64, "_blank");
  if (!w) alert("JobPilot: allow pop-ups for this site, then click the bookmark again.");
}
