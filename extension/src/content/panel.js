// In-page review panel (closed Shadow DOM, so the page's CSS and scripts cannot restyle or read it).
// Shows what was filled, what needs review, what was kept and what was skipped, with the reason for each.
// Buttons only react to real user clicks (event.isTrusted), never to events a page script dispatches.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.panel) return;
  let host = null; let shadow = null;

  const CSS = `
    :host { all: initial; }
    .p { position: fixed; z-index: 2147483646; right: 16px; bottom: 16px; width: min(380px, calc(100vw - 32px)); max-height: 70vh;
         display: flex; flex-direction: column; font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: #111827;
         background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; box-shadow: 0 12px 40px rgba(0,0,0,.18); overflow: hidden; }
    header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #4f46e5; color: #fff; }
    header b { font-size: 13px; }
    button { font: inherit; cursor: pointer; border-radius: 8px; border: 1px solid #d1d5db; background: #fff; color: #111827; padding: 3px 8px; }
    header button { border-color: rgba(255,255,255,.5); background: transparent; color: #fff; }
    .body { overflow: auto; padding: 8px 14px 12px; }
    h4 { margin: 10px 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { padding: 6px 0; border-bottom: 1px solid #f3f4f6; }
    li:last-child { border-bottom: 0; }
    .l { font-weight: 600; }
    .r { color: #4b5563; font-size: 12px; }
    .ok .l::before { content: "✓ "; color: #059669; }
    .rv .l::before { content: "● "; color: #d97706; }
    .nd .l::before { content: "! "; color: #dc2626; }
    .notice { margin: 8px 0 0; padding: 8px; border-radius: 8px; background: #eef2ff; color: #3730a3; }
    .foot { padding: 8px 14px; border-top: 1px solid #f3f4f6; color: #4b5563; font-size: 12px; }
    @media (prefers-color-scheme: dark) {
      .p { background: #111827; color: #f9fafb; border-color: #374151; }
      li { border-color: #1f2937; } .r, .foot { color: #9ca3af; } button { background: #1f2937; color: #f9fafb; border-color: #4b5563; }
      .notice { background: #1e1b4b; color: #c7d2fe; } .foot { border-color: #1f2937; }
    }`;

  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) if (k === "class") e.className = v; else e.setAttribute(k, v);
    for (const k of kids) e.append(k);
    return e;
  }

  function mount() {
    if (host?.isConnected) return;
    host = document.createElement("jobpilot-review");
    shadow = host.attachShadow({ mode: "closed" });
    document.documentElement.append(host);
  }

  function section(title, cls, items, extra) {
    if (!items.length) return null;
    return el("div", {}, el("h4", {}, `${title} (${items.length})`),
      el("ul", { class: cls }, ...items.map((i) => {
        const li = el("li", {}, el("div", { class: "l" }, i.label));
        const why = i.reason || i.note || (i.value ? `Filled: ${String(i.value).slice(0, 80)}` : "");
        if (why) li.append(el("div", { class: "r" }, why));
        extra?.(i, li);
        return li;
      })));
  }

  function show(report) {
    mount();
    shadow.replaceChildren();
    const close = el("button", { type: "button", "aria-label": "Close" }, "Close");
    close.addEventListener("click", (e) => { if (e.isTrusted) host.remove(); });
    const body = el("div", { class: "body" });
    const parts = [
      section("Needs your input", "nd", report.needs),
      section("Please review", "rv", report.review),
      section("Filled", "ok", report.filled),
      section("Kept your existing value", "rv", report.kept, (i, li) => {
        if (!i.replaceable) return;
        const b = el("button", { type: "button" }, "Use JobPilot value");
        b.addEventListener("click", async (e) => {
          if (!e.isTrusted) return;
          b.disabled = true;
          b.textContent = (await JP.useProposed(i.ref)) ? "Replaced" : "Could not replace";
        });
        li.append(b);
      }),
      section("Skipped", "", report.skipped),
    ].filter(Boolean);
    if (!parts.length) parts.push(el("p", {}, "No fillable questions were found on this part of the form."));
    body.append(...parts);
    const counts = `${report.filled.length} filled · ${report.review.length} to review · ${report.needs.length} need you`;
    shadow.append(el("style", {}, CSS), el("div", { class: "p", role: "dialog", "aria-label": "JobPilot review" },
      el("header", {}, el("b", {}, `JobPilot · ${counts}`), close), body,
      el("div", { class: "foot" }, "Check every answer, attach files, then submit the form yourself. JobPilot never submits.")));
  }

  function notice(text) {
    if (!shadow) return;
    const body = shadow.querySelector(".body");
    if (!body) return;
    body.querySelector(".notice")?.remove();
    body.prepend(el("p", { class: "notice" }, text));
  }

  JP.panel = { show, notice };
})();
