---
language: html
tags: [tailwind, components, ui]
title: Tailwind Component Patterns
description: Card, modal, navbar, form, button variants, and dark mode components
source: pattern
---

## Card Component

```html
<div class="max-w-sm rounded-xl overflow-hidden shadow-lg bg-white dark:bg-gray-800 transition-shadow hover:shadow-xl">
  <img class="w-full h-48 object-cover" src="https://placehold.co/400x300" alt="Card image">
  <div class="p-6">
    <div class="flex items-center gap-2 mb-2">
      <span class="px-2 py-1 text-xs font-semibold text-blue-600 bg-blue-100 dark:bg-blue-900 dark:text-blue-200 rounded-full">Category</span>
      <span class="text-sm text-gray-500 dark:text-gray-400">3 min read</span>
    </div>
    <h3 class="text-xl font-bold text-gray-900 dark:text-white mb-2">Card Title</h3>
    <p class="text-gray-600 dark:text-gray-300 mb-4 line-clamp-2">
      This is a description that gets truncated to two lines using line-clamp utility.
    </p>
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <img class="w-8 h-8 rounded-full" src="https://placehold.co/32x32" alt="Avatar">
        <span class="text-sm font-medium text-gray-700 dark:text-gray-200">Jane Doe</span>
      </div>
      <button class="px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
        Read More →
      </button>
    </div>
  </div>
</div>
```

## Modal / Dialog

```html
<!-- Modal overlay -->
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
  <!-- Modal panel -->
  <div class="relative w-full max-w-md mx-4 bg-white dark:bg-gray-800 rounded-2xl shadow-2xl">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Modal Title</h2>
      <button class="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>
    <!-- Body -->
    <div class="px-6 py-4 text-gray-600 dark:text-gray-300">
      <p>Modal content goes here. This can contain forms, text, or any other content.</p>
    </div>
    <!-- Footer -->
    <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
      <button class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 rounded-lg">
        Cancel
      </button>
      <button class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg">
        Confirm
      </button>
    </div>
  </div>
</div>
```

## Navbar

```html
<nav class="sticky top-0 z-40 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200 dark:border-gray-800">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="flex items-center justify-between h-16">
      <!-- Logo -->
      <div class="flex items-center gap-8">
        <span class="text-xl font-bold text-gray-900 dark:text-white">Brand</span>
        <div class="hidden md:flex items-center gap-6">
          <a href="#" class="text-sm font-medium text-gray-700 hover:text-blue-600 dark:text-gray-300 dark:hover:text-blue-400">Home</a>
          <a href="#" class="text-sm font-medium text-gray-700 hover:text-blue-600 dark:text-gray-300 dark:hover:text-blue-400">Features</a>
          <a href="#" class="text-sm font-medium text-gray-700 hover:text-blue-600 dark:text-gray-300 dark:hover:text-blue-400">Pricing</a>
        </div>
      </div>
      <!-- Right side -->
      <div class="flex items-center gap-4">
        <button class="hidden sm:inline-flex px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg">
          Get Started
        </button>
        <!-- Mobile menu button -->
        <button class="md:hidden p-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-200">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</nav>
```

## Form Controls

```html
<form class="max-w-md mx-auto space-y-6 p-6 bg-white dark:bg-gray-800 rounded-xl shadow-sm">
  <!-- Text input with label -->
  <div>
    <label for="email" class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Email</label>
    <input
      id="email"
      type="email"
      placeholder="you@example.com"
      class="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
    >
  </div>

  <!-- Select dropdown -->
  <div>
    <label for="role" class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Role</label>
    <select id="role" class="w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
      <option>Developer</option>
      <option>Designer</option>
      <option>Product Manager</option>
    </select>
  </div>

  <!-- Checkbox -->
  <div class="flex items-center gap-3">
    <input id="terms" type="checkbox" class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500">
    <label for="terms" class="text-sm text-gray-600 dark:text-gray-300">I agree to the terms</label>
  </div>

  <!-- Submit -->
  <button type="submit" class="w-full px-4 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-lg transition-colors">
    Submit
  </button>
</form>
```

## Button Variants

```html
<div class="flex flex-wrap gap-4 p-6">
  <!-- Solid -->
  <button class="px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-lg shadow-sm transition-colors">Primary</button>
  <button class="px-5 py-2.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors">Danger</button>
  <button class="px-5 py-2.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors">Success</button>

  <!-- Outline -->
  <button class="px-5 py-2.5 text-sm font-medium text-blue-600 border border-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">Outline</button>

  <!-- Ghost -->
  <button class="px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 rounded-lg transition-colors">Ghost</button>

  <!-- Size variants -->
  <button class="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-lg">Small</button>
  <button class="px-5 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg">Default</button>
  <button class="px-6 py-3 text-base font-medium text-white bg-blue-600 rounded-lg">Large</button>

  <!-- Disabled -->
  <button disabled class="px-5 py-2.5 text-sm font-medium text-gray-400 bg-gray-200 dark:bg-gray-700 rounded-lg cursor-not-allowed">Disabled</button>

  <!-- Loading / Icon button -->
  <button class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors">
    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/></svg>
    Loading
  </button>
</div>
```

## Dark Mode Wrapper

```html
<!-- Dark mode toggle using Tailwind's dark: variant -->
<div class="min-h-screen bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100 transition-colors">
  <div class="max-w-4xl mx-auto p-8">
    <h1 class="text-3xl font-bold mb-4">Dark Mode Ready</h1>
    <p class="text-gray-600 dark:text-gray-400 mb-6">
      All components use Tailwind's <code class="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">dark:</code> variant for seamless theme switching.
    </p>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Card in dark mode -->
      <div class="p-6 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <h3 class="font-semibold mb-2">Card Title</h3>
        <p class="text-sm text-gray-500 dark:text-gray-400">Content adapts automatically.</p>
      </div>
      <!-- Works with system preference or class toggle -->
      <div class="p-6 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <h3 class="font-semibold mb-2">System Preference</h3>
        <p class="text-sm text-gray-500 dark:text-gray-400">Use <code class="px-1 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">class</code> strategy for manual toggle.</p>
      </div>
    </div>
  </div>
</div>
```