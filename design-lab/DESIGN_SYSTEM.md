# JobPilot design system (v2: cobalt × violet × coral)

Source of truth: `frontend/src/index.css` (tokens) and the shared components listed below. Use tokens, never raw hex or
Tailwind palette colours (emerald/amber/sky/rose… are remapped onto these roles for legacy code, but new code uses roles).

## Colour roles (Tailwind classes)
| Role | Class | Light | Use for |
|---|---|---|---|
| Cobalt | `text-route` `bg-route` `bg-route-tint` (= `primary`) | #365CF5 / tint #EEF1FF | main actions, links, active nav |
| Indigo | `text-heading` `bg-ink` | #29236E | headings, strong contrast, "ink" buttons |
| Violet | `text-violet` `bg-lavender` (`text-info` `bg-info-tint`) | #6A45DC / #EEE9FF | secondary emphasis, selected states, focus ring |
| Coral | `bg-coral` (fills only) `text-coral-ink` `bg-peach` | #FF6B76 / #C8323F / #FFF0EB | small highlights, counts, "to learn" chips |
| Success | `text-success` `bg-success-tint` | #1F7A50 | ONLY confirmed outcomes (submitted, offer, verified) |
| Warning | `text-caution` `bg-caution-tint` | #9E6210 | needs attention |
| Error | `text-destructive` `bg-destructive/10` | #C23A50 | failures, destructive actions |
| Surfaces | `bg-background` `bg-card` `bg-paper-sunk` `bg-muted` | #F8F9FC / #FFF / #F0F2FA | page / card / sunken |
| Text | `text-foreground` `text-muted-foreground` | #171927 / #626879 | |
Dark mode redefines every token; never hard-code dark: variants for these roles.

## Type
- Headings: `font-display` (Manrope), weight 700–800, tracking -0.02 to -0.03em, colour `text-heading`. h1/h2 get this automatically.
- Body/UI: Geist (default `font-sans`), 13–15px.
- Numbers (scores, counts, dates, money): `readout` class (Geist Mono, tabular).
- Small spaced labels: `eyebrow` class (mono caps, 11px). One per section at most.
- Accent word in a heading: `<em>` → violet, upright. Use once per heading, not on every page.
- Page titles: `PageHeader` (26–30px). Never build a custom page title.

## Shape and density
- Cards: `rounded-2xl bg-card ring-1 ring-border`, padding 16–20px. Raised hover only on interactive cards (`hover:shadow-[var(--shadow-raised)]`).
- Avoid "everything is a card": prefer rows/lists inside one container, dividers, and split views.
- Buttons are pills (`Button`); one primary per area. Secondary = `outline`/`ghost`. Dark emphasis = `variant="ink"`.
- Inputs: `Input` (h-10 rounded-xl). Native selects: `NativeSelect`.
- Keep pages compact: first useful content visible at 1440×900 without scrolling; long content scrolls inside its own region (modal/panel), not the whole page.

## Motion (all respect prefers-reduced-motion via the global rule)
- Hover/press: 100–150ms. Selection/tabs: 180–240ms. Sidebar: 260ms. Modal: 240ms in / 150ms out. Page enter: 300ms (`jp-rise`, already on every route).
- Easing: `ease-[cubic-bezier(.2,0,0,1)]` (standard). Transform + opacity only.
- Mount reveals: `animate-in fade-in-0 slide-in-from-top-1 duration-200` (tw-animate-css).
- Tabs content already animates (TabsContent). Dialogs/menus already animate.
- `jp-bump` class: one-shot pop for save/toggle confirmations.

## Voice (subtle Gen Z, never at the cost of clarity)
- OK: headings, empty states, success toasts ("On your radar ✨", "Application sent. Big move.", "All caught up. Love that for you.", "Nothing hitting yet. Let's tweak those filters.").
- NOT: form labels, navigation labels, errors that need action, legal/privacy/security/salary/eligibility/status wording.
- No emoji in headings; at most one in a toast. Never forced slang.

## Shared components
- Layout + collapsible sidebar: `layouts/AppLayout.tsx`, map in `layouts/navigation.ts`, ⌘K `components/app/CommandMenu.tsx`.
- Job row: `components/app/JobCard.tsx` (+ `CompanyMark`).
- Full JD modal: `components/app/JobDetailSheet.tsx` → `JobDetailModal` (alias `JobDetailSheet`). Use it for every "View full JD".
- `PageHeader`, `SkillChips`, `NativeSelect`, `EmptyState`, `ErrorState`, `StatusBadge`, `StageBadge` in `components/app/common.tsx`.
- Illustration: `components/app/DawnScene.tsx` (use sparingly; never above job results).
