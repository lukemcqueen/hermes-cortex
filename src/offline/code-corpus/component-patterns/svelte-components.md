---
language: svelte
tags: [svelte, components, reactive]
title: Svelte Components
description: Props, slots, stores, reactive statements, events, actions
source: pattern
---

## Basic Component with Props

```svelte
<script lang="ts">
  // Props with default values
  export let name: string = 'Guest';
  export let avatar: string | undefined = undefined;
  export let role: 'admin' | 'user' | 'viewer' = 'viewer';
  export let online: boolean = false;

  // Derived / reactive state
  let initials: string;
  $: initials = name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
</script>

<div class="user-chip" class:online>
  {#if avatar}
    <img src={avatar} alt={name} class="avatar" />
  {:else}
    <div class="avatar-fallback">{initials}</div>
  {/if}
  <div class="info">
    <span class="name">{name}</span>
    <span class="role">{role}</span>
  </div>
  <span class="status-dot"></span>
</div>

<style>
  .user-chip { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 1rem; border-radius: 8px; background: #f9fafb; }
  .online { border-left: 3px solid #22c55e; }
  .avatar { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; }
  .avatar-fallback { width: 36px; height: 36px; border-radius: 50%; background: #3b82f6; color: white; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.875rem; }
  .name { font-weight: 500; }
  .role { font-size: 0.75rem; color: #6b7280; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #d1d5db; margin-left: auto; }
  .online .status-dot { background: #22c55e; }
</style>
```

## Events (Component Communication)

```svelte
<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let value: string = '';
  export let placeholder: string = 'Type something...';
  export let maxLength: number = 500;

  const dispatch = createEventDispatcher<{
    submit: string;
    clear: void;
    'update:value': string;
  }>();

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim()) {
        dispatch('submit', value.trim());
      }
    }
  }

  function handleInput(e: Event) {
    const target = e.target as HTMLTextAreaElement;
    dispatch('update:value', target.value);
  }
</script>

<div class="composer">
  <textarea
    {value}
    {placeholder}
    {maxLength}
    on:keydown={handleKeydown}
    on:input={handleInput}
  />
  <div class="footer">
    <span class="count" class:over={value.length > maxLength}>
      {value.length}/{maxLength}
    </span>
    <button on:click={() => dispatch('clear')} disabled={!value}>Clear</button>
  </div>
</div>

<style>
  .composer { border: 1px solid #d1d5db; border-radius: 8px; padding: 0.5rem; }
  textarea { width: 100%; border: none; resize: vertical; min-height: 60px; outline: none; font-family: inherit; }
  .footer { display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem; }
  .count { font-size: 0.75rem; color: #9ca3af; }
  .over { color: #ef4444; }
  button { font-size: 0.875rem; padding: 0.25rem 0.75rem; border-radius: 4px; border: 1px solid #d1d5db; background: white; cursor: pointer; }
</style>
```

## Slots (Named and Fallback)

```svelte
<script lang="ts">
  export let title: string = 'Card';
  export let collapsible: boolean = false;

  let open: boolean = true;
</script>

<div class="card">
  <div class="card-header" class:collapsible on:click={() => collapsible && (open = !open)}>
    <!-- Named slot with fallback -->
    <slot name="title">
      <h3>{title}</h3>
    </slot>
    {#if collapsible}
      <span class="chevron" class:open>{open ? '▾' : '▸'}</span>
    {/if}
  </div>

  {#if open}
    <div class="card-body">
      <!-- Default slot -->
      <slot />
    </div>
  {/if}

  {#if $$slots.footer}
    <div class="card-footer">
      <slot name="footer" />
    </div>
  {/if}
</div>

<style>
  .card { border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
  .card-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem; background: #f9fafb; font-weight: 600; }
  .collapsible { cursor: pointer; user-select: none; }
  .card-body { padding: 1rem; }
  .card-footer { padding: 0.75rem 1rem; border-top: 1px solid #e5e7eb; background: #f9fafb; }
  .chevron { transition: transform 0.2s; }
  .open { transform: rotate(0deg); }
  .chevron:not(.open) { transform: rotate(-90deg); }
</style>
```

## Stores (Reactive State)

```typescript
// stores/theme.ts
import { writable, derived, readonly } from 'svelte/store';

export type ThemeMode = 'light' | 'dark' | 'system';

export const themeMode = writable<ThemeMode>('system');

export const isDark = derived(themeMode, ($mode) => {
  if ($mode === 'dark') return true;
  if ($mode === 'light') return false;
  // system preference
  if (typeof window !== 'undefined') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  return false;
});

export const theme = derived(isDark, ($dark) => ({
  background: $dark ? '#1f2937' : '#ffffff',
  text: $dark ? '#f3f4f6' : '#111827',
  primary: '#3b82f6',
  surface: $dark ? '#374151' : '#f3f4f6',
  border: $dark ? '#4b5563' : '#d1d5db',
}));

export function toggleTheme() {
  themeMode.update(($mode) => {
    if ($mode === 'light') return 'dark';
    if ($mode === 'dark') return 'system';
    return 'light';
  });
}
```

```svelte
<!-- Using stores in components -->
<script lang="ts">
  import { themeMode, isDark, theme, toggleTheme } from './stores/theme';
  import { onMount } from 'svelte';

  // Custom store: persisted to localStorage
  import { persisted } from './stores/persisted';

  // Svelte auto-subscribes when you reference a store with $ prefix
  // $themeMode, $isDark, $theme are auto-subscriptions

  onMount(() => {
    // Apply dark class to document
    const unsubscribe = isDark.subscribe(($dark) => {
      document.documentElement.classList.toggle('dark', $dark);
    });
    return unsubscribe;
  });
</script>

<div class="app" style="background: {$theme.background}; color: {$theme.text};">
  <p>Current mode: {$themeMode}</p>
  <p>Is dark: {$isDark}</p>
  <button on:click={toggleTheme}>Toggle Theme</button>
</div>
```

## Reactive Statements ($:)

```svelte
<script lang="ts">
  export let items: Array<{ id: number; name: string; price: number; quantity: number }> = [];

  // Reactive statements — re-run when dependencies change
  $: subtotal = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  $: tax = subtotal * 0.08;
  $: total = subtotal + tax;
  $: itemCount = items.reduce((sum, item) => sum + item.quantity, 0);
  $: formattedTotal = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(total);

  // Reactive statement with block (side effects)
  $: {
    console.log(`Cart updated: ${itemCount} items, total ${formattedTotal}`);
  }

  // Reactive statement that depends on a condition
  $: freeShipping = total >= 75;
  $: shippingCost = freeShipping ? 0 : 5.99;
  $: grandTotal = total + shippingCost;

  // Grouped reactivity
  $: summary = {
    subtotal,
    tax,
    total,
    freeShipping,
    shippingCost,
    grandTotal,
    itemCount,
  };
</script>

<div class="cart-summary">
  <h3>Cart Summary</h3>
  <div class="line"><span>Items:</span><span>{itemCount}</span></div>
  <div class="line"><span>Subtotal:</span><span>${subtotal.toFixed(2)}</span></div>
  <div class="line"><span>Tax (8%):</span><span>${tax.toFixed(2)}</span></div>
  <div class="line">
    <span>Shipping:</span>
    <span class:free={freeShipping}>{freeShipping ? 'FREE' : `$${shippingCost.toFixed(2)}`}</span>
  </div>
  <div class="line total"><span>Total:</span><span>{formattedTotal}</span></div>
</div>

<style>
  .cart-summary { border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; }
  .line { display: flex; justify-content: space-between; padding: 0.25rem 0; }
  .total { font-weight: 700; font-size: 1.125rem; border-top: 2px solid #e5e7eb; margin-top: 0.5rem; padding-top: 0.5rem; }
  .free { color: #22c55e; font-weight: 500; }
</style>
```

## Actions (use:directive)

```svelte
<script lang="ts">
  import type { Action } from 'svelte/action';

  /* ---------- Custom action: click outside ---------- */
  interface ClickOutsideParams {
    enabled?: boolean;
    callback: () => void;
  }

  const clickOutside: Action<HTMLElement, ClickOutsideParams> = (node, params) => {
    const handleClick = (e: MouseEvent) => {
      if (!params?.enabled ?? true) return;
      if (node && !node.contains(e.target as Node)) {
        params?.callback();
      }
    };

    document.addEventListener('click', handleClick, true);

    return {
      destroy() {
        document.removeEventListener('click', handleClick, true);
      },
      update(newParams: ClickOutsideParams) {
        params = newParams;
      },
    };
  };

  /* ---------- Custom action: tooltip ---------- */
  const tooltip: Action<HTMLElement, string> = (node, text) => {
    const tooltipEl = document.createElement('div');
    tooltipEl.className = 'tooltip';
    tooltipEl.textContent = text;

    function show() {
      const rect = node.getBoundingClientRect();
      tooltipEl.style.cssText = `
        position: fixed; top: ${rect.top - 8}px; left: ${rect.left + rect.width / 2}px;
        transform: translate(-50%, -100%); background: #1f2937; color: white;
        padding: 4px 8px; border-radius: 4px; font-size: 12px;
        white-space: nowrap; pointer-events: none; z-index: 9999;
      `;
      document.body.appendChild(tooltipEl);
    }

    function hide() {
      tooltipEl.remove();
    }

    node.addEventListener('mouseenter', show);
    node.addEventListener('mouseleave', hide);

    return {
      destroy() {
        hide();
        node.removeEventListener('mouseenter', show);
        node.removeEventListener('mouseleave', hide);
      },
      update(newText: string) {
        tooltipEl.textContent = newText;
      },
    };
  };
</script>

<!-- Usage of actions -->
<script lang="ts">
  let dropdownOpen = false;
</script>

<div use:clickOutside={{ enabled: dropdownOpen, callback: () => (dropdownOpen = false) }}>
  <button on:click={() => (dropdownOpen = !dropdownOpen)} use:tooltip={'Click to toggle'}>
    Menu {dropdownOpen ? '▴' : '▾'}
  </button>

  {#if dropdownOpen}
    <div class="dropdown">
      <a href="/profile">Profile</a>
      <a href="/settings">Settings</a>
      <a href="/logout">Logout</a>
    </div>
  {/if}
</div>
```