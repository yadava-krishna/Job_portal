// JobPilot's signature illustration: a dawn sky over layered hills, crossed by a dashed flight path with waypoints.
// Pure SVG drawn from theme variables, so it turns into a night scene in dark mode and costs no image download.
// The path draws itself once on load (CSS, skipped under reduced motion).
import { useId } from "react";
import { cn } from "@/lib/utils";

export function DawnScene({ className, waypoints = 3, plane = true, points, align = "center" }: {
  className?: string; waypoints?: number; plane?: boolean;
  /** Custom waypoints (viewBox units, 1200 × 380) for layouts where the default path would cross text. */
  points?: number[][];
  /** "right" keeps the right edge (where the path flies) in view on tall, narrow panels. */
  align?: "center" | "right";
}) {
  const id = useId().replace(/:/g, "");
  const pts = points ?? [[640, 268], [800, 214], [960, 168], [1110, 104]].slice(0, Math.max(2, Math.min(4, waypoints)));
  return (
    <svg viewBox="0 0 1200 380" preserveAspectRatio={align === "right" ? "xMaxYMax slice" : "xMidYMax slice"} aria-hidden className={cn("block h-full w-full", className)}>
      <defs>
        <linearGradient id={`sky${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" className="[stop-color:var(--scene-sky-1)]" />
          <stop offset="0.55" className="[stop-color:var(--scene-sky-2)]" />
          <stop offset="1" className="[stop-color:var(--scene-sky-3)]" />
        </linearGradient>
        <radialGradient id={`sun${id}`} cx="0.72" cy="0.7" r="0.42">
          <stop offset="0" className="[stop-color:var(--scene-sun)]" stopOpacity="0.95" />
          <stop offset="1" className="[stop-color:var(--scene-sun)]" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={`cloud${id}`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" className="[stop-color:var(--scene-cloud)]" stopOpacity="0.85" />
          <stop offset="1" className="[stop-color:var(--scene-cloud)]" stopOpacity="0" />
        </radialGradient>
        <mask id={`reveal${id}`} maskUnits="userSpaceOnUse" x="0" y="0" width="1200" height="380">
          <path d={`M ${pts.map((p) => p.join(" ")).join(" L ")}`} fill="none" stroke="white" strokeWidth="24" strokeLinecap="round"
                pathLength={1} strokeDasharray="1 1" className="jp-path-draw" />
        </mask>
        <linearGradient id={`fade${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0.55" className="[stop-color:var(--background)]" stopOpacity="0" />
          <stop offset="1" className="[stop-color:var(--background)]" stopOpacity="1" />
        </linearGradient>
      </defs>
      <rect width="1200" height="380" fill={`url(#sky${id})`} />
      <rect width="1200" height="380" fill={`url(#sun${id})`} />
      {/* soft clouds */}
      <ellipse cx="230" cy="96" rx="210" ry="46" fill={`url(#cloud${id})`} />
      <ellipse cx="520" cy="62" rx="170" ry="34" fill={`url(#cloud${id})`} />
      <ellipse cx="1040" cy="80" rx="240" ry="52" fill={`url(#cloud${id})`} />
      <ellipse cx="860" cy="140" rx="150" ry="30" fill={`url(#cloud${id})`} />
      {/* stars, visible only at night */}
      <g className="fill-[var(--scene-star)]">
        {[[80, 40], [190, 70], [330, 30], [460, 92], [610, 44], [760, 24], [900, 58], [1080, 36], [1150, 110], [40, 130]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.4" />)}
      </g>
      {/* hills, far to near */}
      <path d="M0 262 C 180 214 330 236 480 222 S 820 186 960 204 S 1140 216 1200 206 V 380 H 0 Z" className="fill-[var(--scene-hill-1)]" />
      <path d="M0 300 C 160 262 300 284 470 268 S 760 236 900 256 S 1120 270 1200 254 V 380 H 0 Z" className="fill-[var(--scene-hill-2)]" />
      <path d="M0 336 C 200 300 360 322 560 306 S 900 290 1040 304 S 1170 310 1200 300 V 380 H 0 Z" className="fill-[var(--scene-hill-3)]" />
      {/* flight path */}
      <path d={`M ${pts.map((p) => p.join(" ")).join(" L ")}`} fill="none" strokeWidth="2.2" strokeLinecap="round" strokeDasharray="2 9"
            className="stroke-[var(--scene-path)]" mask={`url(#reveal${id})`} />
      {pts.map(([x, y], i) => (
        <g key={i} className="jp-waypoint" style={{ animationDelay: `${300 + i * 260}ms` }}>
          <circle cx={x} cy={y} r="9" className="fill-[var(--scene-path)]" opacity="0.18" />
          <circle cx={x} cy={y} r="4" className="fill-[var(--scene-path)]" />
        </g>
      ))}
      {plane && (() => {
        const [x, y] = pts[pts.length - 1];
        return (
          <g transform={`translate(${x + 26} ${y - 16}) rotate(-24)`} className="jp-waypoint" style={{ animationDelay: "1100ms" }}>
            <path d="M -14 0 L 14 0 M 2 0 L -6 -10 M 2 0 L -6 10 M -12 0 L -16 -5 M -12 0 L -16 5" fill="none" strokeWidth="2.6" strokeLinecap="round" className="stroke-[var(--scene-plane)]" />
          </g>
        );
      })()}
      <rect width="1200" height="380" fill={`url(#fade${id})`} />
    </svg>
  );
}
