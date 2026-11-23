// Simple marks in each portal's brand colour, so the cards are recognisable at a glance. Decorative: the portal's name
// is always written next to it.
import type { PortalKey } from "./types";
import { cn } from "@/lib/utils";

const TILE: Record<PortalKey, string> = { linkedin: "bg-[#0A66C2]", indeed: "bg-[#2557A7]", naukri: "bg-[#275DF5]" };

export function PortalLogo({ portal, className }: { portal: PortalKey; className?: string }) {
  return (
    <span aria-hidden data-logo={portal}
          className={cn("grid size-10 shrink-0 place-items-center rounded-[10px] text-white shadow-[0_1px_2px_rgb(0_0_0/18%)]", TILE[portal], className)}>
      {portal === "linkedin" && <span className="font-sans text-[17px] leading-none font-extrabold tracking-[-0.04em]">in</span>}
      {portal === "naukri" && <span className="font-sans text-[18px] leading-none font-extrabold">N</span>}
      {portal === "indeed" && (
        <svg viewBox="0 0 24 24" className="size-6" fill="none">
          <path d="M5.5 9.2C8.6 5.4 13.6 4 18.6 5.6" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" />
          <circle cx="12.4" cy="10" r="1.9" fill="currentColor" />
          <rect x="10.85" y="12.6" width="3.1" height="7.4" rx="1.4" fill="currentColor" />
        </svg>
      )}
    </span>
  );
}
