---
name: storybook-setup
description: "Set up Storybook with Next.js (Vite) + Tailwind CSS + @storybook/test — init, Tailwind wiring, story patterns, build verification."
version: 1.0.0
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [storybook, nextjs, tailwind, testing, frontend]
    related_skills: [react-component-testing]
---

# Storybook Setup (Next.js + Tailwind + @storybook/test)

## Overview

Set up Storybook in a Next.js project using the `@storybook/nextjs-vite` framework with Tailwind CSS rendering and @storybook/test for interaction tests. This is the proven path for a Next.js (Vite) + Tailwind app — `@storybook/nextjs-vite` handles Next.js-specific features (next/image, next/link) that plain Vite Storybook gets wrong.

## When to Use

- Adding Storybook to a Next.js app (App Router or Pages Router)
- Writing component stories for documentation
- Adding interaction tests with @storybook/test (play functions)
- Verifying Storybook builds cleanly in CI

## Init

```bash
cd apps/web
npx storybook@latest init --yes
pnpm install    # or npm install
```

This creates:
- `.storybook/main.ts` — framework config, stories globs, addons
- `.storybook/preview.tsx` — global decorators, viewport, controls
- `storybook` + `build-storybook` scripts in `package.json`
- Addons: `@chromatic-com/storybook`, `@storybook/addon-vitest`, `@storybook/addon-a11y`, `@storybook/addon-docs`

### Verify the framework was selected

```ts
// .storybook/main.ts
import type { StorybookConfig } from "@storybook/nextjs-vite";

const config: StorybookConfig = {
  framework: {
    name: "@storybook/nextjs-vite",
    options: {},
  },
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"],
  addons: [
    "@storybook/addon-essentials",
    "@chromatic-com/storybook",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
  ],
};
export default config;
```

If the generated config uses `@storybook/react-vite` instead, switch it to
`@storybook/nextjs-vite` and install it:

```bash
pnpm add -D @storybook/nextjs-vite
```

## Wire Tailwind CSS

Storybook doesn't auto-load `globals.css`. Import your Tailwind entry file in `.storybook/preview.tsx`:

```tsx
import type { Preview } from "@storybook/react";
import "../app/globals.css";   // ← your Tailwind entry point (adjust path)

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
  // Optional: wrap all stories with your providers (ThemeProvider, etc.)
  decorators: [
    (Story) => (
      <SomeProvider>
        <Story />
      </SomeProvider>
    ),
  ],
};

export default preview;
```

### Tailwind v4 note

Tailwind v4 uses `@import "tailwindcss";` in CSS (not the v3 `@tailwind`
directives). Storybook reads the same CSS file either way — the import in
preview.tsx is what matters. If utilities aren't applied, confirm the CSS
file actually contains the v4 import and that PostCSS sees it.

## Story Patterns

### Basic story (args-driven)

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "./Button";

const meta = {
  title: "UI/Button",
  component: Button,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "ghost"],
    },
    onClick: { action: "clicked" },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    variant: "primary",
    children: "Save changes",
  },
};

export const Secondary: Story = {
  args: {
    variant: "secondary",
    children: "Cancel",
  },
};
```

### Autodocs

With `tags: ["autodocs"]` and `@storybook/addon-docs`, Storybook generates a
docs page from the story file: props table, story examples, and MDX if
present. Add a `description` to the meta for richer docs.

### Interaction test (@storybook/test)

```tsx
import { expect, userEvent, within } from "@storybook/test";

export const TogglesDropdown: Story = {
  args: { items: ["One", "Two", "Three"] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const toggle = canvas.getByRole("button", { name: /options/i });
    await userEvent.click(toggle);

    await expect(canvas.getByRole("list")).toBeInTheDocument();
    await expect(canvas.getAllByRole("listitem")).toHaveLength(3);
  },
};
```

### Next.js features in stories

`@storybook/nextjs-vite` handles `next/image` and `next/link` out of the box.
If a custom image loader is configured, mock it:

```tsx
// In the story file or preview
import NextImage from "next/image";
// Override the loader via the component's props, or set a default in preview
```

## Run the Tests

```bash
# Run play-function tests (vitest-powered)
pnpm test-storybook
# or with a running dev server: pnpm storybook && pnpm test-storybook --url http://localhost:6006

# CI-friendly: run storybook + tests headless
pnpm test-storybook --ci
```

### test-storybook config

Add to `package.json` or a `storybook.test.ts` entry — the default from init
uses `.storybook` config and the `vitest` addon. Verify the addon is enabled
in main.ts (`@storybook/addon-vitest`).

## Build Verification

```bash
# Production build must succeed
pnpm build-storybook
# Output: storybook-static/

# Sanity checks
test -f storybook-static/index.html && echo "index present"
test -f storybook-static/index.json && echo "index.json present (stories registered)"

# Confirm the build includes your stories (grep a known title)
grep -rl "UI/Button" storybook-static/ | head -1
```

## Pitfalls

- ❌ **Tailwind classes not rendering** — missing `globals.css` import in preview.tsx; or the CSS file path is wrong for the App Router (`app/globals.css` vs `src/app/globals.css`).
- ❌ **`next/image` errors in stories** — wrong framework selected; use `@storybook/nextjs-vite`, not `@storybook/react-vite`.
- ❌ **Fonts/assets missing** — add static dirs in main.ts:
  ```ts
  staticDirs: ["../public"],
  ```
- ❌ **Stories not discovered** — the glob in `main.ts` must match your story file location (`../src/**/*.stories.tsx`).
- ❌ **play functions flaky** — ensure `userEvent` from `@storybook/test` (not RTL's) and `await` every interaction.
- ❌ **`test-storybook` fails with no dev server** — it needs a running Storybook unless `--ci` uses the vitest addon's isolated mode; verify the addon config.
- ❌ **Docs page empty** — `tags: ["autodocs"]` missing, or addon-docs not installed.
- ❌ **Env vars in stories** — `NEXT_PUBLIC_*` vars are inlined at build; ensure the same `.env` is loaded for Storybook (it reads `.env` from project root).

## CI Integration

```yaml
# GitHub Actions snippet
- run: pnpm install
- run: pnpm build-storybook
- run: pnpm test-storybook --ci
```

## Related
- `react-component-testing` — testing patterns (complementary; play functions overlap with RTL)
- `react-best-practices` — quality rules
- `react-composition-patterns` — component structure
- `test-driven-development` — TDD discipline
