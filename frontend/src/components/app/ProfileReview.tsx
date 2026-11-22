// Resume extraction review: what the resume says next to what you confirmed. Parsing never confirms anything; a newer
// resume can only propose changes, which you take or leave field by field before saving.
import type { ReactNode } from "react";
import { FileSearch, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { EditableProfile, ProfileFieldReview, ProfileReview } from "@/types/api";

const STATE_CHIP: Record<string, { text: string; tone: string; title: string }> = {
  extracted: { text: "From resume", tone: "bg-route-tint text-route ring-route/20", title: "Read from your resume. Check it, then save to confirm." },
  missing: { text: "Missing", tone: "bg-caution-tint text-caution ring-caution/25", title: "Not found. Add it yourself." },
  conflict: { text: "Resume differs", tone: "bg-caution-tint text-caution ring-caution/25", title: "Your newer resume says something else." },
  stale: { text: "Check again", tone: "bg-caution-tint text-caution ring-caution/25", title: "Confirmed a while ago and can change." },
};

/** The state chip for one field (nothing for confirmed or empty optional fields). */
export function StateChip({ field }: { field?: ProfileFieldReview }) {
  const c = field ? STATE_CHIP[field.state] : undefined;
  if (!c) return null;
  return (
    <span data-testid={`state-${field!.key}`} title={field!.detail || c.title}
          className={cn("ml-1.5 inline-flex items-center rounded-full px-1.5 py-px align-middle text-[11px] font-medium ring-1 ring-inset", c.tone)}>
      {c.text}
    </span>
  );
}

/** A label with its review chip, for <Field label=…>. */
export function Labelled({ text, field }: { text: string; field?: ProfileFieldReview }) {
  return <>{text}<StateChip field={field} /></>;
}

/** Banner at the top of the form: what needs a look, in plain words. */
export function ReviewBanner({ review }: { review: ProfileReview | null | undefined }) {
  if (!review || review.status === "confirmed") return null;
  const count = (s: string) => review.fields.filter((f) => f.state === s).length;
  const missing = count("missing"), conflict = count("conflict"), stale = count("stale");
  const parts: string[] = [];
  if (conflict) parts.push(`${conflict} ${conflict === 1 ? "section differs" : "sections differ"} on your new resume`);
  if (missing) parts.push(`${missing} ${missing === 1 ? "detail is" : "details are"} missing`);
  if (stale) parts.push(`${stale} ${stale === 1 ? "detail was" : "details were"} confirmed a while ago`);
  return (
    <div role="status" data-testid="profile-review-banner" className="flex gap-3 rounded-xl bg-route-tint/60 p-3.5 text-sm ring-1 ring-route/20">
      <FileSearch className="mt-0.5 size-4 shrink-0 text-route" aria-hidden />
      <div className="min-w-0">
        <p className="font-medium text-heading">
          {review.status === "unconfirmed" ? "Check what we read from your resume" : "Your profile needs a quick look"}
        </p>
        <p className="mt-0.5 text-[13px] text-muted-foreground">
          {review.status === "unconfirmed"
            ? "Nothing here is used for matching or applications until you save. Fix anything we got wrong."
            : "Nothing was changed. Take the resume's version where it's right, keep yours where it isn't, then save."}
          {parts.length > 0 && <> {parts.join(", ")}.</>}
        </p>
      </div>
    </div>
  );
}

/** "New resume says: X · Use this" under a single-value field in conflict. */
export function ScalarSuggestion({ field, onUse }: { field?: ProfileFieldReview; onUse: (v: string) => void }) {
  if (!field || field.state !== "conflict" || typeof field.extracted !== "string") return null;
  return (
    <Suggestion>
      New resume says <span className="font-medium text-foreground">“{field.extracted}”</span>
      <Button size="xs" variant="outline" className="ml-2" onClick={() => onUse(field.extracted as string)}><RefreshCw /> Use this</Button>
    </Suggestion>
  );
}

type ListKey = "skills" | "experience" | "education" | "certifications" | "projects";

const describe = (key: ListKey, item: unknown): string => {
  if (typeof item === "string") return item;
  const o = item as Record<string, unknown>;
  if (key === "experience") return [o.title, o.company].filter(Boolean).join(" at ");
  if (key === "education") return [o.degree, o.institution || o.university].filter(Boolean).join(", ");
  return String(o.name ?? "");
};

/** "Your new resume adds: … · Add" above a list section in conflict. Adds only what you click. */
export function ListSuggestion<K extends ListKey>({ field, listKey, onAdd }: {
  field?: ProfileFieldReview; listKey: K; onAdd: (items: EditableProfile[K]) => void;
}) {
  if (!field || field.state !== "conflict" || !Array.isArray(field.extracted) || !field.extracted.length) return null;
  const items = field.extracted as EditableProfile[K];
  return (
    <Suggestion testId={`suggest-${listKey}`}>
      New resume adds: <span className="text-foreground">{(items as unknown[]).map((i) => describe(listKey, i)).join(" · ")}</span>
      <Button size="xs" variant="outline" className="ml-2" onClick={() => onAdd(items)}><Plus /> Add {items.length === 1 ? "it" : `all ${items.length}`}</Button>
    </Suggestion>
  );
}

function Suggestion({ children, testId }: { children: ReactNode; testId?: string }) {
  return <p data-testid={testId} data-guard-ignore className="flex flex-wrap items-center gap-y-1 rounded-lg bg-caution-tint/60 px-2.5 py-1.5 text-xs text-muted-foreground">{children}</p>;
}

export const reviewField = (review: ProfileReview | null | undefined, key: string) => review?.fields.find((f) => f.key === key);
