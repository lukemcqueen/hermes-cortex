# Rails Admin Stimulus Patterns

Stimulus controller patterns for Rails admin UIs, built and tested on the rails-ioneent-website project (Rails 8.1, Propshaft, esbuild, Docker Compose).

## 1. Media Picker — Browse from media library

Attach a "Browse" button to any text field that accepts an image path. Opens a full-screen modal showing the media library (filtered by folder), lets the user click an image, populates the field.

**Files:** `media_picker_controller.js`, `media/browser.html.erb`

**Wiring:**
```erb
<%= form.hidden_field :image, id: "carousel_image",
    data: { controller: "media-picker",
            media_picker_input_value: "carousel_image",
            media_picker_folder_value: "carousel" } %>
```

**Controller logic:**
- `connect()` wraps the input in a flex container and adds a "📁 Browse" button
- `open()` fetches `/en/media/browser?folder=...&selected=...` (returns just the image grid, no layout)
- `#select(path)` sets the hidden input value, dispatches `input`/`change` events, closes modal
- Modal is created once (`#media-picker-modal`), reused across all picker instances

**Browser endpoint** (`media#browser`):
- Filters images by `params[:folder]`
- Sorts selected image to front
- Renders `media/browser.html.erb` with `layout: false`
- Each image has `data-path` attribute with the relative path (e.g. `a/messgram_001.jpg`)

**Folder mapping:**
| Form | Folder |
|---|---|
| Carousel | `carousel` |
| Artist | `a` |
| News | `news` |
| Shows | `shows` |

## 2. Image Preview — thumbnail replacing text field

Replaces a visible text input with a thumbnail preview + hidden input + Browse + Remove. The user never sees the file path.

**Files:** `preview_image_controller.js`

**Wiring:**
```erb
<div data-controller="preview-image" class="image-preview-field">
  <div class="preview-thumb"
       data-action="click->preview-image#showFull"
       style="display:<%= model.image.present? ? 'block' : 'none' %>;...">
    <img data-preview-image-target="preview" alt="image preview" style="...">
  </div>
  <div class="preview-placeholder" data-preview-image-target="placeholder"
       style="display:<%= model.image.present? ? 'none' : 'flex' %>;...">
    No image
  </div>
  <div class="d-flex gap-2 align-items-center">
    <%= form.hidden_field :image, id: "field_id",
        data: { preview_image_target: "input",
                controller: "media-picker",
                media_picker_input_value: "field_id",
                media_picker_folder_value: "carousel" } %>
    <button type="button" data-preview-image-target="removeBtn"
            data-action="preview-image#remove"
            style="display:<%= model.image.present? ? 'inline-flex' : 'none' %>;...">
      Remove
    </button>
  </div>
</div>
```

**Controller logic:**
- `connect()` → `refresh()` → reads hidden input, sets img src to `/en/media/image?path=...`
- Listens for `change` events on the hidden input (set by media-picker when an image is selected)
- `remove()` clears the hidden input, triggers `change`/`input` events, refreshes UI
- `showFull()` opens a lightbox modal with the full-size image

## 3. Propshaft Image Proxy

Propshaft serves assets with content-digested URLs (`/assets/a/file-<digest>.jpg`). The undigested path (`/assets/a/file.jpg`) returns 404. Since Stimulus controllers in the browser can't compute the digest, images need a proxy endpoint that serves from `app/assets/images/` without digestion.

**Endpoint:**
```ruby
# In MediaController (public, no auth required)
def image
  path = params[:path]
  full = Rails.root.join("app/assets/images", path)
  if full.exist? && full.to_s.start_with?(Rails.root.join("app/assets/images").to_s)
    send_file full, disposition: :inline, type: Rack::Mime.mime_type(File.extname(path))
  else
    head :not_found
  end
end
```

**Route:** `GET /:locale/media/image?path=<relative_path>`

**Usage in JS:** `fetch(\`/en/media/image?path=${encodeURIComponent(path)}\`)` or set as img src.

**Security:** The path guard (`start_with?`) prevents directory traversal. No authentication needed — only admin surfaces use this endpoint.

## 4. Flash Toast — auto-dismissing notifications

Replaces Bootstrap inline alerts with a fixed bottom-right toast that auto-dismisses after 4 seconds.

**Files:** `toast_controller.js`, `_notices_alerts.html.erb`

**Template structure:**
```erb
<div id="flash-toast-container" style="position:fixed;bottom:24px;right:24px;z-index:99999;max-width:420px;">
  <div class="flash-toast flash-toast-notice" data-controller="toast"
       style="background:#1a1a1a;border:1px solid #d4a853;border-radius:8px;...">
    <span><%= notice %></span>
    <button data-action="click->toast#dismiss" ...>&times;</button>
  </div>
</div>
```

**Controller logic:**
- `connect()` starts a 4-second timer → `dismiss()`
- `dismiss()` fades out (opacity → 0, translateY → 10px), removes element after 350ms
- Removes the container div if it's the last toast
- Close button calls `dismiss()` immediately

**Animation:**
```css
@keyframes flash-in {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

## 5. Reordering with Up/Down Buttons

Swap `sort_order` values between adjacent records via POST.

**Controller action:**
```ruby
def move
  @slide = CarouselSlide.find(params[:id])
  neighbor = if params[:direction] == "up"
    CarouselSlide.where("sort_order < ?", @slide.sort_order).order(sort_order: :desc).first
  else
    CarouselSlide.where("sort_order > ?", @slide.sort_order).order(:sort_order).first
  end
  if neighbor
    new_order = neighbor.sort_order
    neighbor.update_column(:sort_order, @slide.sort_order)
    @slide.update_column(:sort_order, new_order)
  end
  redirect_to action: :index
end
```

**View:**
```erb
<%= button_to "▲", move_carousel_slide_path(slide, direction: "up"), method: :post,
    disabled: idx == 0 %>
<%= button_to "▼", move_carousel_slide_path(slide, direction: "down"), method: :post,
    disabled: idx == @slides.size - 1 %>
```

## Critical Pitfalls

### Pitfall 1: Empty `src=""` triggers onerror before controller connects

The browser treats `src=""` as the current page URL and immediately fires `onerror`. If the onerror handler replaces the parent's innerHTML, it destroys the img element before the Stimulus controller can set the real src.

**Fix:** Omit the `src` attribute entirely on the initial render:
```erb
<img data-preview-image-target="preview" alt="..." style="...">
```
The controller sets `this.previewTarget.src = url` in `connect()` → `refresh()`.

Also make the onerror handler defensive:
```html
onerror="if(this.src&&this.src!==window.location.href){ ... }"
```

### Pitfall 2: Duplicate Stimulus target names

When both a parent div and its child img have the same target name:
```html
<div data-preview-image-target="preview">
  <img data-preview-image-target="preview" ...>
</div>
```

`this.previewTarget` returns the **first** element in DOM order (the div), not the img. Setting `.src` on a div has no effect.

**Fix:** Put the target only on the element you need to manipulate:
```html
<div class="preview-thumb" data-action="click->preview-image#showFull">
  <img data-preview-image-target="preview" ...>
</div>
```

### Pitfall 3: Lightbox modal visible by default blocks all clicks

The `#ensureLightbox()` pattern creates a lightbox div with `position:fixed;top:0;left:0;right:0;bottom:0` backdrop. If the outer div has default `display:block`, the overlay is visible immediately on page load — covering the entire viewport and intercepting all clicks.

```javascript
// BAD — visible immediately
const div = document.createElement("div")
div.id = "preview-lb"
div.innerHTML = `<div id="preview-lb-backdrop" style="display:flex;position:fixed;top:0;left:0;right:0;bottom:0;z-index:99999;...">`

// GOOD — hidden until showFull() is called
const div = document.createElement("div")
div.id = "preview-lb"
div.style.display = "none"  // ← critical
```

### Pitfall 4: Lightbox persists across Turbo navigations

The lightbox is appended to `document.body` once. When navigating away from the edit page (via Turbo), the lightbox remains in the DOM. If it's not `display:none`, it covers the next page.

**Fix:** Start hidden (pitfall 3) AND clean up on Turbo navigation:
```javascript
disconnect() {
  const lb = document.getElementById("preview-lb")
  if (lb && !document.querySelector("[data-controller=\"preview-image\"]")) {
    lb.remove()
  }
}
```

The `disconnect()` runs when the Stimulus controller is torn down (Turbo replaces the page content). Only remove if no other preview-image controllers remain on the page.

### Pitfall 5: media-picker wraps hidden inputs but the wrapper breaks layout

The media-picker `connect()` wraps the input in a `d-flex align-items-center` container and adds a Browse button. When the input is `type="hidden"`, the wrapper still renders with zero-height content. The Browse button appears but the layout may look odd.

**Fix:** Keep the Browse button inside the preview-image container's button row (`d-flex gap-2`), not wrapped with the hidden input. The media-picker still targets the hidden input for value manipulation but the visual button is managed by the parent layout.
