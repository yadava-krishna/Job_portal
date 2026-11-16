// Resume attachment. Runs only after the user clicks "Attach resume" and picked which resume to use.
//
// Chrome lets an extension's content script populate an <input type=file> with a DataTransfer whose File it built
// itself (no file system access involved). Success is never assumed: the input is read back (name, size, type), the
// site's own "file attached" indicator is checked when the adapter knows it, and visible upload errors are reported.
(() => {
  const JP = (globalThis.__jobpilot ??= { adapters: {} });
  if (JP.resume) return;
  const { waitFor, errorTextFor, textOf } = JP.dom;

  const MIME = { pdf: "application/pdf", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" };

  function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  /** Does the input's accept attribute allow this file? An empty accept allows anything. */
  function accepts(input, name, type) {
    const accept = (input.accept || "").toLowerCase().split(",").map((s) => s.trim()).filter(Boolean);
    if (!accept.length) return true;
    const ext = "." + String(name).split(".").pop().toLowerCase();
    return accept.some((a) => a === "*" || a === "*/*" || a === ext || a === type || (a.endsWith("/*") && type.startsWith(a.slice(0, -1))) ||
      (ext === ".docx" && /word|officedocument/.test(a)));
  }

  function uploadError(input) {
    const t = errorTextFor(input) || textOf(input.closest("[class*='upload'], [class*='file'], .field, li")?.querySelector("[role=alert], [class*='error']"));
    return /(not (supported|allowed)|too large|exceeds|invalid|failed|error|could not|unable)/i.test(t || "") ? t : "";
  }

  /** Attach `file` ({name, type, b64}) to the adapter's resume input. Returns {ok, verified, name, size, reason?}. */
  async function attach(adapter, file, { replace = false } = {}) {
    const input = adapter.resumeInput?.();
    if (!input) return { ok: false, manual: true, reason: "No resume upload field was found on this page. Use Download resume and attach it yourself." };
    if (input.disabled) return { ok: false, manual: true, reason: "The resume field is disabled." };
    const already = (input.files && input.files.length) || adapter.hasResume?.();
    if (already && !replace) return { ok: false, needsConfirm: true, reason: "A resume is already attached. Click Replace to use the one you chose instead." };
    const type = file.type || MIME[String(file.name).split(".").pop().toLowerCase()] || "application/octet-stream";
    if (!accepts(input, file.name, type)) {
      const kind = /\.docx$/i.test(file.name) ? "Word" : "PDF";
      return { ok: false, manual: true, reason: `This form does not accept ${kind} files (it accepts: ${input.accept}). Choose another format or attach a file yourself.` };
    }
    const bytes = b64ToBytes(file.b64);
    try {
      const f = new File([bytes], file.name, { type, lastModified: Date.now() });
      const dt = new DataTransfer();
      dt.items.add(f);
      input.files = dt.files;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    } catch {
      return { ok: false, manual: true, reason: "This page did not allow attaching the file automatically. Use Download resume and attach it yourself." };
    }
    // Read back what the page now holds. Some sites move the file elsewhere and clear the input: then the adapter's
    // own indicator decides.
    const got = await waitFor(() => {
      const err = uploadError(input);
      if (err) return { err };
      const f = input.files?.[0];
      if (f && f.name === file.name && f.size === bytes.length) return { f };
      if (adapter.hasResume?.()) return { indicator: true };
      return null;
    }, 4000);
    if (got?.err) return { ok: false, manual: true, reason: `The site reported a problem with the file: "${got.err.slice(0, 160)}".` };
    if (!got) return { ok: false, manual: true, reason: "The page did not accept the file. Use Download resume and attach it yourself." };
    return { ok: true, verified: true, name: file.name, size: bytes.length, how: got.f ? "input" : "site indicator", note: adapter.afterResumeNote };
  }

  /** The file(s) the form currently holds for each file question (for the review). */
  function attachments(adapter, questions) {
    return questions.filter((q) => q.kind === "file").map((q) => {
      const input = q.els[0];
      const files = [...(input.files || [])].map((f) => ({ name: f.name, size: f.size }));
      const isResume = input === adapter.resumeInput?.();
      const attached = files.length > 0 || (isResume && Boolean(adapter.hasResume?.()));
      return { ref: q.ref, label: q.label || (isResume ? "Resume" : "File"), required: Boolean(q.required), isResume, files, attached,
               error: uploadError(input) || null };
    });
  }

  JP.resume = { attach, attachments, accepts };
})();
