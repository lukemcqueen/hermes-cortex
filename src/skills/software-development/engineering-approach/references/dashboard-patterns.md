# Dashboard Patterns (acme-platform)

FastAPI + Jinja2 admin dashboard for the platform. Runs as its own Docker container
with Docker socket mount so it can query all compose projects.

## Adding a new component to the dashboard

### 1. Compose stub

Create `{component}/compose.yaml` so `docker compose ps` can discover its containers.
Minimal stub works for placeholder:

```yaml
name: acme-{component}
services: {}
```

Docker Compose v2 matches containers by project name label, so even an empty compose
file with the right `name:` picks up running containers from the actual service repo.

### 2. COMPONENTS list (dashboard/app.py)

Insert into the `COMPONENTS` list in display order. App services go before infra:

```python
COMPONENTS = [
    ("acme-works",     "Works",     "🎵"),
    ("acme-royalty",   "Royalty",   "💰"),
    # ... app services first ...
    ("keycloak",         "Identity",  "🔑"),
    # ... infra services last ...
]
```

Each entry is `(slug, label, icon)`. The slug must match the directory name and
compose project name.

### 3. Skeleton card count (templates/index.html)

Update the loading skeleton array to match the new total:

```js
grid.innerHTML = Array(14).fill(0).map(() =>
```

### 4. Root ./run COMPONENTS array

Add to `COMPONENTS=(...)` in root `run` script. Same ordering as dashboard.

### 5. .env.example

Create `{component}/.env.example` documenting all env vars with sections:
- REQUIRED (no defaults — passwords, secrets)
- PORTS (customizable host-facing ports)
- OPTIONAL (commented out, sensible defaults in code)

### 6. Rebuild

```bash
./run dashboard down && ./run dashboard build && ./run dashboard up
```

## i18n: Korean-first bilingual UI

### Design

- **ko is default**, en is secondary (user preference: Korean music rights domain)
- Client-side: translations embedded in JS object, no server round-trip
- Persists in `localStorage` key `acme_lang`
- Server passes `lang` query param to template (`?lang=ko|en`)

### Translations map

```js
const TRANSLATIONS = {
  ko: { refresh: '새로고침', start: '시작', stop: '중지', /* ... */ },
  en: { refresh: 'Refresh',  start: 'Start',  stop: 'Stop',   /* ... */ },
};
```

### Translation function

```js
function t(key, vars) {
  const lang = localStorage.getItem('acme_lang') || 'ko';
  let text = (TRANSLATIONS[lang] && TRANSLATIONS[lang][key]) || key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace('{' + k + '}', v);
    }
  }
  return text;
}
```

Use `vars` for parameterized strings like `t('running_badge', { n: 3 })` → `'● 3개 실행'`.

### Language switcher

Two buttons (KO / EN) in the header. Active state toggled by class. On click:
1. Set `localStorage`
2. Update HTML `lang` attribute
3. Re-translate all `[data-i18n]` elements
4. Re-render dynamic content (cards, detail, summary)

Static server-rendered text (title, HTML lang attr) uses Jinja2 `{{ ... if lang == "en" else ... }}`.

### Font stack

Include both fonts for proper Korean glyph rendering:

```css
font-family: 'Inter', 'Noto Sans KR', -apple-system, ...;
```

### Skeleton container cards

When data is loading, show 14 (or current component count) skeleton cards:
```js
Array(14).fill(0).map(() =>
  `<div class="card" style="pointer-events:none"><div class="skeleton" style="height:80px"></div></div>`
).join('')
```
Keep this number synced with the actual COMPONENTS list count.

### Pitfalls

- **`data-i18n` only covers static HTML.** Dynamic content (cards, detail panel, toasts) must call `t(key)` in JS. Don't forget `applyTranslations()` re-runs after lang switch.

- **Skeleton count must match COMPONENTS length.** If you add a component but forget the skeleton array `Array(N)`, the loading state shows wrong placeholder count.

- **Toasts use template strings with `t()` calls** — pass `{ name: '...' }` vars, don't concatenate strings around translated text.

- **Badge labels use parameterized counts** — `t('running_badge', { n: s.running })` ensures Korean/English pluralization is correct per locale.

- **Never call `renderCards()` from `setLang()`.** Rebuilding the entire card list on every language switch causes visible DOM delay. Instead:
  1. Add `data-i18n="${'comp_' + name}"` to the card-name span in `renderCards()`.
  2. `applyTranslations()` updates card names in-place without DOM rebuild.
  3. `renderDetail()` (rebuilds detail panel) and `refreshSummary()` (updates badges) are still needed in `setLang()`.

- **`getElementById` with `.toUpperCase()` ID construction is fragile.** `document.getElementById('lang' + lang.toUpperCase())` breaks because IDs are case-sensitive (`#langEn` ≠ `'#langEN'`). Prefer `data-lang` attributes and `querySelector`:
  ```html
  <button class="lang-btn" data-lang="ko" onclick="setLang('ko')">KO</button>
  ```
  ```js
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.lang-btn[data-lang="${lang}"]`).classList.add('active');
  ```
  This is immune to ID casing mismatches and cleaner than string construction.

- **Component labels from backend are not translatable.** `comp.label` is a server-side string. To translate component names client-side:
  1. Add translation keys like `'comp_acme-website': '웹사이트'` to the TRANSLATIONS map.
  2. Use `t('comp_' + name)` in `renderCards()` and `renderDetail()` instead of `comp.label`.
  3. Add `data-i18n="${'comp_' + name}"` to the detail title name span so `applyTranslations()` updates it.

- **`document.title` must be set explicitly in `setLang()`.** The `<title>` element's `data-i18n="appTitle"` may or may not update via `applyTranslations()` depending on the browser (some don't reflect `<title>` textContent changes visually). Always add `document.title = t('appTitle')` as a backup in `setLang()`.

- **Polling races don't break language switching if `t()` reads from localStorage.** Since `refreshAll()` → `renderCards()` → `t()` → `getLang()` → `localStorage.getItem('acme_lang')`, the polling interval preserves the user's language choice without any coordination with `setLang()`.

## Card rendering: container stats on cards

Each component card now shows running/total container count and healthy count:

```js
function renderCards() {
  let html = '';
  for (const [name, comp] of Object.entries(data.components)) {
    const sc = statusClass(comp.status);
    const containerInfo = comp.total > 0
      ? `${comp.running}/${comp.total} ${t('containers_label')}${comp.healthy > 0 ? ` · ${comp.healthy} ${t('healthy_label')}` : ''}`
      : t('noContainers');
    html += `
      <div class="card ${isActive ? 'active' : ''}" tabindex="0" role="button"
           onclick="selectComponent('${name}')"
           onkeydown="if(event.key==='Enter'||event.key===' ')selectComponent('${name}')">
        <div class="status-bar ${sc}"></div>
        <div class="card-top">
          <span class="card-icon">${comp.icon}</span>
          <span class="card-status-dot ${sc}"></span>
          <span class="card-name" data-i18n="${'comp_' + name}">${t('comp_' + name)}</span>
          <span class="card-subtitle">${name}</span>
        </div>
        <div class="card-stats">
          <span class="card-stat">
            <span class="card-stat-value">${comp.running}</span>
            <span class="card-stat-label">/${comp.total} ${t('containers_label')}</span>
          </span>
          ${comp.healthy > 0 ? `<span class="card-stat"><span class="card-stat-value" style="color:var(--green)">${comp.healthy}</span> <span class="card-stat-label">${t('healthy_label')}</span></span>` : ''}
        </div>
      </div>`;
  }
}
```

The card structure:
- `.status-bar` — thin colored bar at top (green=running, yellow=degraded, red=stopped)
- `.card-icon` — emoji for the component type
- `.card-status-dot` — small circle indicator (same colors as status bar)
- `.card-name` — translated display name with `data-i18n` for language switching
- `.card-subtitle` — raw component identifier (e.g., `acme-matching`)
- `.card-stats` — new row showing running/total containers and healthy count

**Conditional rendering:** `comp.total === 0` shows `t('noContainers')` ("컨테이너 없음"). `comp.healthy === 0` hides the healthy stat entirely.

## Control actions with exit_code error handling

The `controlComponent()` function dispatches start/stop/restart commands via the API.
It checks `body.exit_code` (not just HTTP status) to detect Docker command failures:

```js
async function controlComponent(action, component) {
  const res = await fetch(`/api/control/${action}/${component}`, { method: 'POST' });
  const body = await res.json();
  if (body.exit_code !== 0) {
    showToast(t('controlFailed', { action, name: component }), 'error');
    return;
  }
  showToast(t('controlSuccess', { action, name: component }), 'success');
  setTimeout(refreshAll, 2000);
}
```

**Why `exit_code` is necessary:** Docker Compose API commands (e.g., `docker compose up`) may return HTTP 200 even when the underlying command fails (non-zero exit code). The `exit_code` field in the API response is the only reliable indicator. Without this check, clicking "Start" on a broken component would show a green success toast even though nothing started.

**Refresh delay:** `refreshAll()` is called after a 2-second delay (not immediately) to give Docker daemon time to update container states after the command completes.

### State dot CSS classes

```css
.state-dot.running { background: var(--green); }
.state-dot.exited  { background: var(--red); }
.state-dot.restarting { background: var(--yellow); }
.state-dot.stopped { background: transparent; border: 2px solid var(--text-secondary); }
```

Note the `.stopped` class uses `transparent` fill + border stroke pattern so containers show as an empty circle. The `.restarting` yellow class was added after the initial CSS omitted it.

## Layout: left panel + right detail pane

The dashboard uses a two-panel layout. Clicking a component selects it and shows
its detail/logs.

- **Left panel (`.panel-left`, 340px)** — scrollable vertical list of component
  cards. Each card shows icon, status dot, translated name, and raw slug.
  Active card highlighted with accent border.
- **Right panel (`.panel-right`, flex 1)** — always-visible detail pane with
  container table and log stream. Placeholder until a component is selected.

CSS:
```css
.container { display: flex; gap: 20px; align-items: flex-start; }
.panel-left { width: 340px; min-width: 340px; flex-shrink: 0; }
.panel-right { flex: 1; min-width: 0; }
.card-grid { display: flex; flex-direction: column; gap: 10px; }
```

Cards are compact horizontal (icon + name + slug) with no stats row.

### Auto-select first component

On load, the first component is selected automatically:

```js
function selectFirstComponent() {
  if (data && data.components) {
    const names = Object.keys(data.components);
    if (names.length > 0 && !selectedComponent) {
      selectComponent(names[0]);
    }
  }
}
```

Called at the end of `refreshAll()`. Mobile: stacks vertically ≤720px.

### Pitfall: click same component deselects (toggle antipattern)

The original `selectComponent` toggled: clicking the already-selected component
set `selectedComponent = null`, which triggered the placeholder text. Fix — always
select, never toggle:

```js
function selectComponent(name) {
  if (selectedComponent === name) return; // Already selected, no-op
  selectedComponent = name;
  renderCards();
  renderDetail();
}
```

## Testing the dashboard

Tests live in `dashboard/tests/`. Run with `./run dashboard test`.

### Core technique: mock `_run_dc`, not subprocess

`dashboard/app.py` abstracts Docker calls behind `_run_dc(component, *args)` which
returns `{"exit_code": N, "stdout": "...", "stderr": "..."}`.  Tests replace this
with an async function that returns canned output:

**conftest.py** (autouse fixture):
```python
@pytest.fixture(autouse=True)
def _mock_run_dc(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_run_dc(component: str, *args: str) -> dict[str, Any]:
        return {"exit_code": 0, "stdout": "", "stderr": ""}
    monkeypatch.setattr("dashboard.app._run_dc", _fake_run_dc)
```

Per-test override:
```python
async def _run(component, *args):
    return {"exit_code": 0, "stdout": '{"ID":"c1","Name":"web","State":"running"}'}
monkeypatch.setattr("dashboard.app._run_dc", _run)
```

Helper for canned responses:
```python
def _make_run_dc_result(stdout="", stderr="", exit_code=0):
    return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}
```

**Why mock `_run_dc` instead of `asyncio.create_subprocess_exec`:**
- `_run_dc` has a `compose.yaml exists` check that fires before the subprocess call
- Mocking at the subprocess level requires a monkeypatch of `PLATFORM_DIR` (fragile)
- `_run_dc` returns a simple dict — the mock is trivial and covers 100% of code paths

### Template directory in test context

The app uses Jinja2Templates with a relative `directory='templates'` path that only
works inside Docker. Fix in conftest:

```python
@pytest.fixture(autouse=True)
def _fix_template_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    here = Path(__file__).resolve().parent.parent  # dashboard/
    real_templates = here / "templates"
    from starlette.templating import Jinja2Templates as _J2
    monkeypatch.setattr("dashboard.app.templates", _J2(directory=str(real_templates)))
```

### Test categories

| Group | Coverage |
|---|---|
| `/health` | Returns `{"status":"ok"}` |
| `/api/status` (aggregate) | 15 components present; stopped/running/degraded/empty; port parsing; summary counts; partial running |
| `/api/status/{component}` (single) | Known component, unknown → 404, running count, empty |
| `/api/control/{action}/{component}` | Start/stop/restart, unknown → 404, invalid action → 400, error → 500 |
| `/api/logs/{component}` (SSE) | Known → event stream, unknown → 404 |
| Dashboard HTML | KO default, EN/KO explicit, invalid lang fallback, all components in HTML, data-i18n attrs, JS functions, language switcher |
| Unit helpers | `_dt()` (None, empty, ISO, garbage), `_parse_containers()` (empty, invalid JSON, no ports, port pubs, uptime, lowercase fields) |

### Dependencies

Add to `dashboard/requirements.txt`:
```
pytest>=8,<9
httpx>=0.28,<1
pytest-asyncio>=1.2,<2
```

### `./run dashboard test`

Wired in the root `run` script:
```bash
test)
    shift 2
    cd "$SCRIPT_DIR" && python3 -m pytest dashboard/tests/ "$@"
    ;;
```

This chdirs to the project root so `dashboard/tests/` resolves correctly,
and passes extra pytest args (`-v`, `-k pattern`, etc.).
