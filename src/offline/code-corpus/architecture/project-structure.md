---
language: typescript
tags: [architecture, project-structure, modular, organization]
title: Project Structure Patterns
description: Feature-based vs layer-based layout, monorepo structure, module boundaries, and domain-driven package organization
source: pattern
---

```typescript
// === PATTERN 1: Feature-Based Structure (recommended for most apps) ===
//
// src/
//   features/
//     auth/
//       components/       # UI components scoped to auth
//       hooks/            # React hooks (useAuth, useLogin)
//       api/              # API client calls (login, logout, refresh)
//       types.ts          # Auth-specific types (User, Session, Credentials)
//       utils.ts          # Auth utilities (token parsing, password helpers)
//       index.ts          # Public barrel — exports only what's consumed externally
//       __tests__/
//     users/
//       components/
//       hooks/
//       api/
//       types.ts
//       utils.ts
//       index.ts
//     dashboard/
//       components/
//       hooks/
//       api/
//       types.ts
//       index.ts
//   shared/
//     ui/                 # Design system (Button, Card, Modal, etc.)
//     lib/                # Pure utilities (formatDate, classNames, validators)
//     api/                # Base HTTP client, interceptors, error mappers
//     hooks/              # Shared hooks (useDebounce, useMediaQuery)
//     types/              # Cross-cutting domain types
//   app/                  # App shell: routing, layout, providers, store
//     router.tsx
//     layout.tsx
//     providers.tsx
//   config/               # App-wide configuration (env, constants, feature flags)

// Feature module boundary — strict barrel pattern
// features/auth/index.ts
export { AuthProvider } from './components/AuthProvider';
export { useAuth } from './hooks/useAuth';
export type { User, Session, LoginCredentials } from './types';

// Internal only — NOT exported from barrel
// These are implementation details hidden from consumers
// import { refreshToken } from './api/refreshToken'; // internal use only
```

```typescript
// === PATTERN 2: Layer-Based Structure (traditional) ===
//
// src/
//   controllers/       # Request handling, input validation, response formatting
//   services/          # Business logic, orchestrations
//   repositories/      # Data access, ORM queries, external API calls
//   models/            # Domain entities, database schemas
//   middleware/        # Express/Koa middleware (auth, logging, rate-limit)
//   routes/            # Route definitions and wiring
//   utils/             # Shared helpers
//   types/             # Global type definitions

// Typical controller
// controllers/userController.ts
import { Request, Response } from 'express';
import { UserService } from '../services/UserService';
import { CreateUserDto } from '../models/user';

export class UserController {
  constructor(private userService: UserService) {}

  async create(req: Request, res: Response): Promise<void> {
    const dto: CreateUserDto = req.body;
    const user = await this.userService.create(dto);
    res.status(201).json(user);
  }
}
```

```typescript
// === PATTERN 3: Monorepo Structure (Nx / Turborepo style) ===
//
// packages/
//   core/              # Shared domain logic, pure functions, interfaces
//     src/
//       domain/
//       utils/
//     package.json
//     tsconfig.json
//   api/               # Backend application
//     src/
//       features/
//       app/
//     package.json
//     tsconfig.json
//   web/               # Frontend application
//     src/
//       features/
//       app/
//     package.json
//     tsconfig.json
//   shared-types/      # Shared type definitions across packages
//     src/
//       index.ts
//     package.json
// tools/
//   eslint-config-custom/
//   tsconfig-custom/
// apps/                # (alternative: keep deployable apps here)
//   admin/
//   public-site/

// Package-level tsconfig paths for clean internal imports
// packages/core/tsconfig.json
{
  "compilerOptions": {
    "paths": {
      "@myorg/core/*": ["./src/*"]
    }
  }
}

// Referencing another package via workspace dependency
// packages/api/package.json
{
  "name": "@myorg/api",
  "dependencies": {
    "@myorg/core": "workspace:*"
  }
}

// Import from another package
// packages/api/src/features/users/UserService.ts
import { Email, UserId } from '@myorg/core/domain';
```

```typescript
// === PATTERN 4: Domain-Driven Package Layout ===
//
// src/
//   bounded-contexts/
//     billing/
//       domain/           # Entities, value objects, domain events
//         Invoice.ts
//         Payment.ts
//         Subscription.ts
//       application/      # Use cases / application services
//         GenerateInvoice.ts
//         ProcessPayment.ts
//       infrastructure/   # Repositories, external adapters
//         StripeProvider.ts
//         PostgresInvoiceRepo.ts
//       interface/        # REST controllers, GraphQL resolvers, CLI commands
//         InvoiceController.ts
//     inventory/
//       domain/
//         Product.ts
//         StockLevel.ts
//       application/
//         ReserveStock.ts
//         CheckAvailability.ts
//       infrastructure/
//         InventoryRepo.ts
//       interface/
//         InventoryController.ts
//   shared-kernel/        # Ubiquitous shared types (NOT generic utilities)
//     Money.ts
//     Address.ts
//     Currency.ts
//   infrastructure/       # Cross-cutting infrastructure
//     database/
//     messaging/
//     cache/

// Domain entity example
// billing/domain/Invoice.ts
export class Invoice {
  private constructor(
    public readonly id: InvoiceId,
    public readonly customerId: CustomerId,
    private _status: InvoiceStatus,
    private _lineItems: LineItem[],
    public readonly createdAt: Date,
  ) {}

  static create(customerId: CustomerId, items: LineItem[]): Invoice {
    return new Invoice(
      InvoiceId.generate(),
      customerId,
      InvoiceStatus.PENDING,
      items,
      new Date(),
    );
  }

  markPaid(): void {
    if (this._status !== InvoiceStatus.PENDING) {
      throw new Error('Only pending invoices can be marked as paid');
    }
    this._status = InvoiceStatus.PAID;
  }

  get status(): InvoiceStatus {
    return this._status;
  }

  get total(): Money {
    return this._lineItems.reduce(
      (sum, item) => sum.add(item.total),
      Money.zero(),
    );
  }
}
```

```typescript
// === MODULE BOUNDARY GUIDELINES ===
//
// 1. Every feature/context exports ONLY through a barrel (index.ts)
// 2. Internal modules are NEVER imported from outside their boundary
//    // ❌ Bad: crossing module boundary into internals
//    import { refreshToken } from '../features/auth/api/refreshToken';
//    // ✅ Good: using the public barrel
//    import { useAuth } from '../features/auth';
//
// 3. Shared code goes in shared/, NOT in a feature folder
// 4. Circular imports are prevented by:
//    - Keeping types in a separate types.ts within each module
//    - Using interfaces for cross-module contracts
//    - Extracting shared abstractions upward
// 5. Dependency direction: shared/ ← features/ ← app/
//    (layers only depend left-to-right, never right-to-left)
```

```typescript
// === ENFORCEMENT: ESLint import boundary rules ===
//
// .eslintrc.js — prevents cross-boundary imports
module.exports = {
  plugins: ['import'],
  rules: {
    // No importing from deep paths inside a feature
    'import/no-internal-modules': [
      'error',
      {
        allow: [
          '**/index',       // Only barrels
          '**/__tests__/*', // Test imports
        ],
      },
    ],
    // Prevent circular dependencies
    'import/no-cycle': ['error', { maxDepth: Infinity }],
    // No relative parent imports beyond the module boundary
    'import/no-relative-parent-imports': 'error',
  },
};
```