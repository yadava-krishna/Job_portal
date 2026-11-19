import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect } from "@/components/app/common";
import { AnswerBank } from "@/components/app/ProfileExtras";
import { errorMessage } from "@/lib/api";
import { useSaveFacts } from "@/services/queries";
import type { VerifiedFacts } from "@/types/api";
import { RememberedAnswers } from "@/features/apply/RememberedAnswers";
import { FieldGroup, Panel } from "./primitives";

const yesNo = [{ value: "", label: "Ask me each time" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }];

/** Verified screening answers plus the saved-answer bank (one save covers both), then the answers remembered while applying. */
export function AnswersSection({ facts }: { facts?: VerifiedFacts }) {
  const save = useSaveFacts();
  const [f, setF] = useState<VerifiedFacts>({});
  useEffect(() => { if (facts) setF(facts); }, [facts]);
  const text = (k: keyof VerifiedFacts, label: string, ph: string, className?: string) => (
    <Field label={label} htmlFor={`f-${k}`} className={className}>
      <Input id={`f-${k}`} value={(f[k] as string | null | undefined) ?? ""} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value || null })} />
    </Field>
  );
  return (
    <div className="space-y-5">
      <Panel title="Verified screening answers"
             description={<>Applications ask these often. JobPilot never guesses them: leave a field empty and it is shown as "needs your input".</>}>
        <div className="space-y-6">
          <FieldGroup title="Pay and availability">
            <div className="grid gap-4 sm:grid-cols-2">
              {text("current_ctc", "Current CTC (optional, only if you want it shared)", "e.g. 6.5 LPA")}
              {text("expected_ctc", "Expected CTC", "e.g. 8-9 LPA")}
              {text("notice_period", "Notice period", "e.g. 30 days")}
              {text("earliest_start_date", "Earliest start date", "e.g. 1 Dec 2026")}
            </div>
          </FieldGroup>
          <FieldGroup title="Work and eligibility">
            <div className="grid gap-4 sm:grid-cols-2">
              {text("work_authorization", "Work authorization", "e.g. Indian citizen")}
              <Field label="Need visa sponsorship?">
                <NativeSelect value={f.requires_sponsorship == null ? "" : f.requires_sponsorship ? "yes" : "no"} onChange={(v) => setF({ ...f, requires_sponsorship: v === "" ? null : v === "yes" })}
                              options={yesNo} className="w-full" />
              </Field>
              <Field label="Willing to relocate?">
                <NativeSelect value={f.willing_to_relocate == null ? "" : f.willing_to_relocate ? "yes" : "no"} onChange={(v) => setF({ ...f, willing_to_relocate: v === "" ? null : v === "yes" })}
                              options={yesNo} className="w-full" />
              </Field>
              {text("shift_flexibility", "Shift flexibility", "e.g. Open to US shifts")}
              {text("relevant_experience", "Relevant experience", "e.g. 4 years in accounts receivable", "sm:col-span-2")}
            </div>
          </FieldGroup>
          <div className="border-t pt-5">
            <AnswerBank facts={f} onChange={setF} />
          </div>
          <div data-save-bar className="flex items-center justify-end gap-3">
            <Button onClick={() => save.mutate({ ...f, custom_answers: (f.custom_answers ?? []).filter((a) => a.question.trim() && a.answer.trim()) }, { onSuccess: () => toast.success("Saved. Locked in."), onError: (e) => toast.error(errorMessage(e)) })} disabled={save.isPending}>
              {save.isPending && <Loader2 className="animate-spin" />} Save answers
            </Button>
          </div>
        </div>
      </Panel>
      <RememberedAnswers />
    </div>
  );
}
