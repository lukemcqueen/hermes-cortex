# Admin Form — Collapsible Sections Pattern

## Problem

Rails admin forms with 40+ fields (artist pages, news, shows, etc.) overwhelm users with a flat list of inputs. Repetitive field groups (Links 1-7, Press 1-3, Songs 1-3, Videos 1-3, Images 1-7) dominate the page and make essential fields hard to find.

## Solution

Collapsible sections using a lightweight Stimulus controller. Core sections (Status, Basic Info, Social Links) stay open by default. Repetitive/long-tail sections (Links, Press, Songs, Videos) start collapsed.

## Stimulus Controller

```javascript
// app/javascript/controllers/collapse_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["body"]

  connect() {
    if (this.element.dataset.collapseDefault === "closed") {
      this.bodyTarget.style.display = "none"
      this.element.classList.add("is-collapsed")
    }
  }

  toggle() {
    const isOpen = this.bodyTarget.style.display !== "none"
    this.bodyTarget.style.display = isOpen ? "none" : ""
    this.element.classList.toggle("is-collapsed", isOpen)
  }
}
```

Register in `index.js`:
```javascript
import CollapseController from "./collapse_controller.js"
application.register("collapse", CollapseController)
```

## View Pattern

```erb
<div class="admin-form-section" data-controller="collapse" data-collapse-default="closed">
  <div class="admin-form-section-title" data-action="click->collapse#toggle" style="cursor:pointer;">
    <span>Section Name</span>
    <span style="float:right;font-size:0.7rem;opacity:0.4;">&#9660;</span>
  </div>
  <div data-collapse-target="body">
    <!-- fields here -->
  </div>
</div>
```

- Add `data-collapse-default="closed"` for sections that start collapsed
- Omit it (or set to "open") for sections that start visible
- The `&#9660;` (▼) indicator should point down — no rotation needed since collapsed content is simply hidden

## Which Sections to Collapse

| Section | Default | Reason |
|---|---|---|
| Status & Settings | Open | Always needed |
| Basic Info | Open | Core data |
| Event/Venue Details | Open | Core data |
| Social Links | Open | Quick to scan |
| Content/Description | Open | Primary content |
| Images | Open | Visual preview useful |
| Links (1-7) | **Closed** | Long, repetitive, rarely all used |
| Press (1-3) | **Closed** | Infrequently needed |
| Songs (1-3) | **Closed** | Optional media |
| Videos (1-3) | **Closed** | Optional media |

## Admin Form Design System

Use these CSS classes for consistent dark-themed admin forms:

- `.admin-form-page` — outer wrapper with proper nav-aware padding
- `.admin-form-title` — gold-colored heading
- `.admin-form-section` — dark card with border, rounded corners, 20px margin-bottom
- `.admin-form-section-title` — gold uppercase label with section separator
- `.admin-form-subsection` — nested section with subtle bottom border
- `.admin-form-subsection-title` — dimmed label
- `.admin-form .form-control` — dark inputs with gold focus ring
- `.admin-form .form-label` — uppercase label
- `.admin-form .btn-primary` — gold pill button
- `.admin-form-errors` — red error card
