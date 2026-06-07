# Design.md

## 1. Philosophy

* Clean, modern, minimal
* Function first, beauty through clarity
* Generous whitespace over density
* Consistency > creativity

**Dark mode variant** (Cortex Dashboard): Uses `--bg: #0a0e17`, `--card: #111827`, zinc-950 base with SF Mono/JetBrains Mono font stack. All spacing, color, and typography rules from this document apply with inverted luminance.

---

## 2. Typography

* **Font stack**: Inter, system-ui, sans-serif
* **Scale**:

  * H1: 32–40px / bold
  * H2: 24–28px / semibold
  * H3: 18–20px / medium
  * Body: 14–16px / regular
  * Caption: 12–13px / light
* **Line height**: 1.4–1.6
* Avoid more than 2 font weights per section

---

## 3. Color System

* **Primary**: #111111 (text, main UI)
* **Secondary**: #666666 (muted text)
* **Background**: #FFFFFF
* **Surface**: #F7F7F7
* **Accent**: #4F46E5 (actions, highlights)
* **Border**: #E5E5E5

Rules:

* Use accent sparingly (≤10%)
* Maintain high contrast
* Prefer neutral palettes

---

## 4. Spacing System (8pt grid)

* XS: 4px
* SM: 8px
* MD: 16px
* LG: 24px
* XL: 32px
* XXL: 48px

Rules:

* Always use consistent spacing scale
* Increase whitespace for hierarchy, not borders

---

## 5. Layout

* Max width: 1200px
* Content padding: 16–24px
* Use grid or flex (avoid absolute positioning)
* Align to left; avoid unnecessary centering
* Clear visual hierarchy: top → bottom flow

---

## 6. Components

### Buttons

* Height: 40–48px
* Radius: 8–12px
* Primary: filled accent
* Secondary: outline or subtle background
* Minimal shadows

### Cards

* Background: white
* Radius: 12–16px
* Padding: 16–24px
* Border: 1px solid #E5E5E5
* Shadow: very subtle or none

### Inputs

* Height: 40–48px
* Border: light gray
* Focus: accent outline
* Labels always visible

---

## 7. Interaction

* Transitions: 150–250ms ease
* Hover: slight opacity or elevation
* Avoid heavy animations
* Feedback must be immediate and clear

---

## 8. Visual Style

* Minimal shadows
* Soft rounded corners (8–16px)
* Flat design with subtle depth
* Avoid clutter, gradients, and noise

---

## 9. Content Style

* Short, clear, direct
* No fluff
* Functional tone
* Labels > placeholders

---

## 10. Do / Don’t

**Do**

* Use whitespace to group elements
* Keep layouts simple and predictable
* Maintain consistency across screens

**Don’t**

* Overuse colors or accents
* Mix too many styles
* Add unnecessary decoration