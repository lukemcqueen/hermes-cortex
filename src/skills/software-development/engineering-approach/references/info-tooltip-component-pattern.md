# InfoTooltip Component Pattern

A reusable hover/focus tooltip for explaining complex concepts on data-heavy pages.

## Component

Location: `components/InfoTooltip.tsx`

```tsx
'use client';

interface InfoTooltipProps {
  text: string;
  className?: string;
}

export default function InfoTooltip({ text, className = '' }: InfoTooltipProps) {
  return (
    <span className={`group relative inline-flex items-center ${className}`}>
      <svg className="h-4 w-4 cursor-help text-gray-400 hover:text-gray-600 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4" />
        <path d="M12 8h.01" />
      </svg>
      <span className="invisible group-hover:visible group-focus-within:visible absolute bottom-full left-1/2 z-10 mb-2 w-56 -translate-x-1/2 rounded-md bg-gray-900 px-3 py-2 text-xs text-white shadow-lg opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-all pointer-events-none">
        {text}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
      </span>
    </span>
  );
}
```

## Behavior

- Renders a `?` circle icon (help icon) next to content
- On hover/focus, shows a dark tooltip box above the icon with a downward-pointing arrow
- `w-56` width — good for 1-3 sentence explanations
- Uses CSS-only approach (no JS state) — `group-hover` and `group-focus-within`
- `pointer-events-none` on the tooltip so it doesn't capture clicks
- Tailwind `group` utility for parent-child hover state

## Usage

Place inline in table headers or next to form labels:

```tsx
<th>
  ISWC <InfoTooltip text="International Standard Musical Work Code — unique identifier for musical works, assigned by CISAC member societies" />
</th>

<label>
  Status <InfoTooltip text="The current lifecycle stage of this distribution run" />
</label>
```

## Best Practices

- Tooltip text should be 1-3 sentences — concise but complete
- Don't use for critical information that must always be visible (tooltips require interaction)
- Don't nest inside `<span>` or `<p>` tags that already have `group` classes (conflicts with the `group` utility)
- Use consistent `text` prop shape across all tooltips: `"ConceptName — explanation"` or `"What it is: description"`
- Pair with `EmptyState` component for a complete UX treatment of table pages

## Related Concepts

- Use during UX gap analysis (see `ux-gap-analysis-methodology.md`) — tooltips are a P1 fix for complex fields
- Existing pattern: `DeductionHelpTooltip` in dashboard components — similar concept but dialog-based. `InfoTooltip` is lighter (CSS-only, no JS state).
