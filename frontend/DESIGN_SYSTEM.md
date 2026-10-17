# CleanData Studio — Design System

All tokens live in `src/index.css` (`@theme`). Tailwind turns them into utilities, so use the
names below instead of raw values. Components live in `src/components/ui/`.

## Colour

| Token | Use |
|---|---|
| `background` `#fff` | Cards, top bar, sidebar, tables |
| `canvas` `#f6f8fb` | App background, table headers, footers of cards |
| `foreground` `#0f172a` | Primary text (slate-900) |
| `muted-foreground` `#5b6b82` | Secondary text |
| `border` `#e2e8f0` / `border-strong` `#cbd5e1` | Card/table borders / form controls |
| `primary` `#2563eb` (+ `primary-hover`, `primary-soft`) | Primary actions, active navigation, links |
| `accent` `#4f46e5` (+ `accent-soft`) | Secondary emphasis only (icons in lists) |
| `success` / `warning` / `danger` (+ `-soft`) | Status. Always paired with an icon or text — never colour alone |
| `chart-1` … `chart-6` | Chart series. Missing values use amber (a status), types use the chart palette |

No gradients except the single subtle canvas→white fade behind the landing hero.

## Typography

Inter (self-hosted via `@fontsource-variable/inter`).

| Class | Size / line | Use |
|---|---|---|
| `text-display` | 42/47 | Landing hero headline only |
| `text-h1` | 24/32 | Page and workspace view titles |
| `text-h2` | 18/26 | Section titles |
| `text-h3` | 15/22 | Card titles |
| `text-body` | 14/22 | Default UI text |
| `text-small` | 13/20 | Tables, form labels, secondary text |
| `text-caption` | 12/16 | Hints, table headers, metadata |
| `text-micro` | 11/14 | Badges, sidebar labels (`.eyebrow`) |
| `text-stat` | 26/32 | KPI values (always with `.tabular`) |

Numbers in tables and KPIs use `.tabular` (tabular figures).

## Spacing, radius, elevation

- 4 px grid (Tailwind spacing). Common steps: 1 (4px), 2 (8px), 3 (12px), 4 (16px), 5 (20px), 6 (24px), 8 (32px).
- Card padding: `p-4` for KPI tiles, `px-5 py-4` for card header/content. Gaps between cards: `gap-4` (dashboard) / `gap-5` (sections).
- Page gutters: `px-4 sm:px-6`; workspace content max width 1280 px.
- Radius: `rounded-md` (6px) controls, `rounded-lg` (8px) cards, `rounded-xl` (12px) large illustration frames.
- Shadows: `shadow-card` (cards), `shadow-raised` (dialogs, toasts, tooltips, product preview). Nothing heavier.
- Layout constants: top bar `h-topbar` (56px), sidebar `w-sidebar` (240px).

## Components

| Component | File | Notes |
|---|---|---|
| Button | `button.tsx` | `primary`, `secondary`, `ghost`, `danger`, `danger-outline`, `link`; sizes `sm`/`md`/`lg`/`icon`; `loading` shows a spinner and disables |
| Card, CardHeader, CardTitle, CardDescription, CardContent | `card.tsx` | The only card style in the product |
| Badge | `badge.tsx` | Tones: neutral, primary, accent, success, warning, danger |
| Alert | `alert.tsx` | Icon + title + text; `role=alert` for errors |
| Input, Select, Label, FieldHint, Checkbox, RadioCard | `form.tsx` | Every control has a visible label |
| Dialog | `dialog.tsx` | Native `<dialog>`: focus trap, Escape, backdrop click |
| Tooltip | `tooltip.tsx` | Hover + focus, linked with `aria-describedby`; works around disabled buttons |
| Toast | `toast.tsx` | Success / error / info feedback after actions |
| Table, THead, TH, TR, TD, RowNumberCell, TableContainer | `table.tsx` | Every table uses these |
| Segmented | `segmented.tsx` | Small view switches (radiogroup) |
| PageHeader, StatCard | `page.tsx` | Title row of each view; KPI tiles |
| Spinner, LoadingBlock, EmptyState, ProgressBar, Meter | `misc.tsx` | Loading, empty and progress states |

## Icons and charts

- Lucide outline icons only, 16px in controls (`size-4`), 20px in feature tiles. No emoji.
- Recharts only where a chart says more than a number: missing values per column (bar) and column types (donut + labelled legend). Charts have no animation, light grid lines and text alternatives.

## Interaction states

Every interactive element has hover, `:focus-visible` (2px primary outline), disabled (50% opacity, no pointer events) and, for async actions, a loading state. Destructive actions open a confirmation dialog. Empty and error states use `EmptyState` / `Alert` with a next step.

## Demo content

The landing page preview uses an explicitly labelled sample dataset ("Demo preview — sample data"). It never appears inside the workspace, where every number comes from the user's file.
