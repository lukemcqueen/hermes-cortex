---
language: typescript
tags: [config, util]
title: tsconfig.json Setup
description: Strict mode, path aliases, module resolution, target, and lib configuration.
source: reference
---

```typescript
{
  "compilerOptions": {
    /* Strict mode — enables all strict checks */
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "noUncheckedIndexedAccess": true,

    /* Module resolution */
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],

    /* Path aliases — must match bundler config too */
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@utils/*": ["src/utils/*"]
    },

    /* Output */
    "outDir": "./dist",
    "rootDir": "./src",
    "sourceMap": true,
    "declaration": true,

    /* Interop */
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "**/*.test.ts"]
}

```
