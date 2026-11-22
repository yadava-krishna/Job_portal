// Job preferences from Discover: the same form as Settings -> Job preferences, in a side sheet, with the same
// unsaved-changes guard (save / discard / keep editing) when it is closed with edits.
import { useEffect, useRef } from "react";
import { ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { LoadingState } from "@/components/app/common";
import { PreferencesForm } from "@/components/app/forms";
import { useUnsavedGuard } from "@/components/settings/UnsavedGuard";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { usePreferences } from "@/services/queries";

type Confirm = (go: () => void) => void;

export function PreferencesSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  // The guard lives in the sheet's body (mounted only while open); it hands its confirm() up for closing.
  const confirm = useRef<Confirm | null>(null);
  const guarded: Confirm = (go) => (confirm.current ? confirm.current(go) : go());
  const navigate = useNavigate();
  return (
    <Sheet open={open} onOpenChange={(o) => (o ? onOpenChange(true) : guarded(() => onOpenChange(false)))}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 data-[side=right]:sm:max-w-2xl" data-testid="preferences-sheet">
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle className="font-display text-[19px] font-bold text-heading">Your job preferences</SheetTitle>
          <SheetDescription className="text-[13px]">
            What you're after and how strict matching is. Saving re-scores your open jobs; this list updates when it's done.{" "}
            <button type="button" className="inline-flex items-center gap-0.5 rounded text-route hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                    onClick={() => guarded(() => { onOpenChange(false); navigate("/settings?tab=preferences"); })}>
              Open in Settings <ExternalLink className="size-3" />
            </button>
          </SheetDescription>
        </SheetHeader>
        <Body confirmRef={confirm} />
      </SheetContent>
    </Sheet>
  );
}

function Body({ confirmRef }: { confirmRef: React.MutableRefObject<Confirm | null> }) {
  const prefs = usePreferences();
  const guard = useUnsavedGuard("discover-preferences");
  confirmRef.current = guard.confirm;
  useEffect(() => () => { confirmRef.current = null; }, [confirmRef]);
  return (
    <>
      <div ref={guard.bodyRef} key={guard.resetKey} className="px-5 py-5" data-dirty={guard.dirty || undefined}>
        {prefs.isError ? <p role="alert" className="text-sm text-destructive">Couldn't load your preferences. Close this and try again.</p>
          : prefs.data ? <PreferencesForm initial={prefs.data.is_configured ? prefs.data : undefined} /> : <LoadingState />}
      </div>
      {guard.dialog}
    </>
  );
}
