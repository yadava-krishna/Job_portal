// Back from a portal's sign-in page (LinkedIn, Indeed). Keeps only the OAuth response fields in this tab's
// sessionStorage, where the signed-in app (Settings → Portal Connections) picks them up and sends them to the JobPilot
// server, which checks that the sign-in was started by the same JobPilot account. Then returns to a fixed in-app page:
// nothing from the URL decides where you go, and location.replace keeps the code out of the browser history.
(function () {
  var q = new URLSearchParams(window.location.search);
  var keep = {};
  ["code", "state", "error", "error_description", "iss"].forEach(function (k) {
    var v = q.get(k);
    if (v) keep[k] = v.slice(0, 4096);
  });
  try {
    if (keep.state) window.sessionStorage.setItem("jobpilot.oauthReturn", JSON.stringify(keep));
  } catch (e) {
    /* storage blocked: Settings shows "start again" */
  }
  window.location.replace("./#/settings?tab=portals");
})();
