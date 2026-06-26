# Rails Propshaft — npm font file 404 fix

## Problem

SCSS imports from npm packages that include `@font-face` with relative font file paths fail in Rails with propshaft. Example: `bootstrap-icons` CSS references `./fonts/bootstrap-icons.woff2`, which the browser resolves to `/assets/fonts/bootstrap-icons.woff2` — a path the asset pipeline doesn't serve.

The font files exist in `node_modules/` but are never copied to `public/assets/` or any path propshaft serves. Result: 404 on the font file → browser shows empty "tofu" boxes instead of icons.

## Fix — CDN import

Replace the local npm SCSS import with a CDN `@import url(...)`:

```scss
// Before (broken — font files 404)
@import 'bootstrap-icons/font/bootstrap-icons';

// After (works — CDN serves font files)
@import url("https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css");
```

## Why the local path doesn't work

The npm package's `bootstrap-icons.css` has:
```css
@font-face {
  font-family: "bootstrap-icons";
  src: url("./fonts/bootstrap-icons.woff2?...") format("woff2");
}
```

When sass inlines this into the compiled application CSS, the relative path `./fonts/` resolves relative to the final CSS URL (`/assets/application-{hash}.css`), producing `/assets/fonts/bootstrap-icons.woff2`. Propshaft does not serve files from `/assets/fonts/` by default — it serves from digest-mapped paths.

## Alternatives considered

1. **Copy font files to `app/assets/fonts/`** — doesn't work because propshaft digest-maps the file, so the relative URL in the CSS (`./fonts/`) points to a non-digested path
2. **Override @font-face in custom CSS** — CSS cascade means the first `@font-face` for `bootstrap-icons` wins, so a local override must appear BEFORE the npm import, which is impractical with sass
3. **CDN import** — works reliably, no asset pipeline config needed, no font files to manage

## Verification

```javascript
// Browser console — check font loaded
document.fonts.ready.then(() => {
  console.log(document.fonts.check('1em bootstrap-icons'));
});
```
