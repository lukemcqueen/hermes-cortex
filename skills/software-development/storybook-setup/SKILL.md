--- Full content (truncated) ---
---
name: storybook-setup
description: "Set up Storybook with Next.js (Vite) + Tailwind CSS + @storybook/test — init, Tailwind wiring, story patterns, build verification."
version: 1.0.0
author: Titus
license: MIT
metadata:
  hermes:
    tags: [storybook, nextjs, tailwind, testing, frontend]
    related_skills: [react-component-testing]
---

# Storybook Setup (Next.js + Tailwind + @storybook/test)

## Overview

Set up Storybook in a Next.js project using the `@storybook/nextjs-vite` framework with Tailwind CSS rendering and @storybook/test for interaction tests.

## Init

```bash
cd apps/web
npx storybook@latest init --yes
pnpm install    # or npm install
```

This creates `.storybook/main.ts`, `.storybook/preview.tsx`, adds `storybook` and `build-storybook` scripts to `package.json`, and installs addons: `@chromatic-com/storybook`, `@storybook/addon-vitest`, `@storybook/addon-a11y`, `@storybook/addon-docs`.

## Wire Tailwind CSS

Storybook doesn't auto-load `globals.css`. Add a decora
... [truncated]
--- End skill ---