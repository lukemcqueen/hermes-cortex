---
language: typescript
tags: [config, util]
title: Declaration Files (.d.ts)
description: Global type declarations, module augmentation, ambient declarations for JS libs.
source: reference
---

```typescript
// ── types/globals.d.ts ──
// Ambient global variable
declare const APP_VERSION: string;

// Global interface augmentation
interface Window {
  analytics?: {
    track(event: string, data?: Record<string, unknown>): void;
  };
}

// Ambient module declaration for untyped JS lib
declare module 'old-js-library' {
  export function doSomething(config: Record<string, unknown>): void;
  export const VERSION: string;
}

// ── types/env.d.ts ──
// Augment existing module
declare namespace NodeJS {
  interface ProcessEnv {
    NODE_ENV: 'development' | 'production' | 'test';
    API_KEY: string;
    DATABASE_URL: string;
  }
}

// ── types/images.d.ts ──
// Declare module for non-code imports
declare module '*.svg' {
  const content: string;
  export default content;
}

declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}

// Usage throughout app:
// const key: string = process.env.API_KEY;
// if (APP_VERSION === '1.0.0') { ... }
// import config from 'old-js-library';

```
