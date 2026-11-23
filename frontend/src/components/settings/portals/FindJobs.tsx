// "Find or import jobs": the four ways a portal job reaches JobPilot, each opening the real flow (Discover filtered to
// the portal, guided link import, the clipper's setup, the alert-mailbox setup), and where it goes next.
import { useState } from "react";
import { ArrowRight, Bookmark, Inbox, Link2, ListFilter } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ClipperCard } from "@/components/app/forms";
import { EmailSection } from "@/components/settings/EmailSection";
import { useEmailIntegration } from "@/services/queries";
import { PLATFORM, type Portal } from "./types";

function Tile({ icon, title, children, action }: { icon: React.ReactNode; title: string; children: React.ReactNode; action: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-xl p-3.5 ring-1 ring-border">
      <h4 className="flex items-center gap-2 text-[13.5px] font-semibold text-heading">{icon}{title}</h4>
      <div className="flex-1 text-xs leading-relaxed text-muted-foreground">{children}</div>
      <div>{action}</div>
    </div>
  );
}

export function FindJobs({ portals, onImport }: { portals: Portal[]; onImport: () => void }) {
  const navigate = useNavigate();
  const email = useEmailIntegration();
  const [sheet, setSheet] = useState<"clipper" | "email" | null>(null);
  const mailbox = email.data?.enabled && email.data.has_password;
  return (
    <section aria-labelledby="find-jobs" className="mt-6" data-testid="find-jobs">
      <h3 id="find-jobs" className="font-display text-[15px] font-bold text-heading">Find or import jobs</h3>
      <p className="mt-0.5 mb-3 text-xs text-muted-foreground">No portal login needed for any of these.</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile icon={<ListFilter className="size-4 text-route" aria-hidden />} title="Browse your JobPilot listings"
              action={<Button size="sm" variant="outline" onClick={() => navigate("/discover")}>All listings <ArrowRight /></Button>}>
          <p>Jobs already in JobPilot, by where they came from:</p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {portals.map((p) => (
              <li key={p.portal}>
                <button type="button" onClick={() => navigate(`/discover?platform=${PLATFORM[p.portal]}`)}
                        className="rounded-full bg-paper-sunk px-2.5 py-0.5 text-[11.5px] font-medium text-foreground ring-1 ring-border transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                  {p.name} · {p.capabilities.listings?.count ?? 0}
                </button>
              </li>
            ))}
          </ul>
        </Tile>
        <Tile icon={<Link2 className="size-4 text-route" aria-hidden />} title="Import a job link"
              action={<Button size="sm" onClick={onImport}><Link2 /> Import a link</Button>}>
          Paste a LinkedIn, Naukri or Indeed job link. JobPilot recognises the portal and job, you add the details, then review and save.
        </Tile>
        <Tile icon={<Bookmark className="size-4 text-route" aria-hidden />} title="Use the clipper"
              action={<Button size="sm" variant="outline" onClick={() => setSheet("clipper")}>Set up the clipper</Button>}>
          A bookmark that copies the job page you're viewing into JobPilot for review, only when you click it.
        </Tile>
        <Tile icon={<Inbox className="size-4 text-route" aria-hidden />} title="Job alert e-mails"
              action={<Button size="sm" variant="outline" onClick={() => setSheet("email")}>{mailbox ? "Manage alert e-mails" : "Connect your mailbox"}</Button>}>
          {mailbox ? <>Reading alerts from <b className="text-foreground">{email.data!.username}</b>{email.data!.last_error ? <span className="text-caution"> · last check failed</span> : null}.</>
            : "Off. JobPilot reads job-alert e-mails only after you connect your own mailbox with an app password."}
        </Tile>
      </div>
      <p className="mt-3 text-xs text-muted-foreground" data-testid="next-steps">
        Then: <b className="text-foreground">Prepare application</b> → choose a resume → verified answers → open the posting on the portal → tell
        JobPilot what happened.
      </p>
      <Sheet open={!!sheet} onOpenChange={(o) => !o && setSheet(null)}>
        <SheetContent className="w-full overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
          <SheetHeader className="pr-12">
            <SheetTitle className="font-display text-[17px] font-bold text-heading">{sheet === "clipper" ? "Browser job clipper" : "Job alert e-mails"}</SheetTitle>
            <SheetDescription className="text-xs">
              {sheet === "clipper" ? "Works on job pages you open yourself. It never crawls or runs in the background."
                : "Connect only your own mailbox. JobPilot reads job-alert messages from the folder you choose, nothing else."}
            </SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-6">{sheet === "clipper" ? <ClipperCard /> : sheet === "email" ? <EmailSection /> : null}</div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
