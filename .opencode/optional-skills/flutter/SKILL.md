---
name: flutter
description: |
  Build, refactor, and test Flutter apps using clean architecture,
  state management, and responsive UI.

  Triggers when user mentions:
  - "flutter"
  - "dart"
  - "mobile app"
  - "widget"
  - "flutter refactor"
  - "flutter ui"
---

# Flutter

## Purpose
Create and refactor Flutter apps that are:
- cleanly structured
- testable
- responsive
- production-ready

---

## Output (STRICT ORDER)

1. **Code**
2. **Explanation** (≤3 sentences)
3. **Tests / Verification**

---

## Workflow (STRICT)

1. Identify intent: feature, bug, refactor, UI, or performance
2. Inspect existing structure (widgets, state, services)
3. Follow existing architecture
4. Keep widgets small and focused
5. Move logic out of UI
6. Add/update tests
7. Run verification
8. Make minimal, safe changes

---

## Architecture Rules

### UI Layer (Widgets)

- StatelessWidget by default
- Use StatefulWidget only when needed
- Keep widgets small (<100 lines)
- Avoid business logic in UI

---

### State Management

Prefer existing approach:

- Provider
- Riverpod
- Bloc
- setState (only for simple local state)

Rules:
- keep state predictable
- avoid global mutable state
- separate UI from state logic

---

### Domain / Services

Move logic into:

```txt
lib/services/
lib/repositories/
lib/domain/
```

Use for:

* API calls
* data transformation
* business rules

---

## UI Rules

* use consistent spacing (8pt grid)
* prefer composition over nesting
* use built-in widgets before custom ones
* ensure responsiveness across screen sizes
* support light/dark mode if enabled

---

## Layout Patterns

### Basic Layout

```dart
Scaffold(
  appBar: AppBar(title: Text('Title')),
  body: Padding(
    padding: EdgeInsets.all(16),
    child: Column(
      children: [],
    ),
  ),
)
```

---

## Navigation

* use Navigator or router package consistently
* avoid hardcoded routes scattered across files
* centralize route definitions if possible

---

## Async Handling

* use `FutureBuilder` or state management
* handle loading/error states explicitly
* avoid silent failures

---

## Testing (MANDATORY)

Use:

* unit tests → business logic
* widget tests → UI behavior
* integration tests → flows

Example:

```dart
testWidgets('displays title', (tester) async {
  await tester.pumpWidget(MyApp());
  expect(find.text('Title'), findsOneWidget);
});
```

---

## Refactoring Rules

* preserve behavior first
* extract widgets before adding complexity
* reduce nesting
* improve readability
* do not rewrite entire screens unnecessarily

---

## Performance

* avoid unnecessary rebuilds
* use const constructors when possible
* use ListView.builder for large lists
* optimize expensive widgets

---

## Commands

```bash
flutter pub get
flutter run
flutter test
flutter analyze
```

---

## Verification Order

```txt
targeted widget test
→ unit tests
→ integration tests
→ flutter analyze
→ manual UI check
```

---

## Accessibility

* support screen readers
* use semantic widgets
* ensure contrast
* support scalable text

---

## Anti-Patterns

Avoid:

* large monolithic widgets
* business logic in UI
* excessive nesting
* skipping tests
* ignoring rebuild performance
* inconsistent state management
* silent async errors

---

## Final Report

```md
## Result
What changed.

## Files changed
- path: purpose

## Verification
- command: result

## Notes
UI behavior, performance, follow-ups
```

---

## Goal

Produce clean, responsive, testable Flutter apps that:

* scale to production
* are easy to maintain
* behave consistently across devices