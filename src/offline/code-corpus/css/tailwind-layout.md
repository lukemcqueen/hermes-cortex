---
language: html
tags: [tailwind, css, responsive, layout]
title: Tailwind Responsive Layout
description: Flex, grid, container, breakpoints, and spacing patterns
source: pattern
---

## Responsive Flex Layout

```html
<!-- Flex row wrapping on mobile, side-by-side on desktop -->
<div class="flex flex-col md:flex-row gap-4 p-4">
  <div class="flex-1 bg-blue-100 p-6 rounded-lg">Column 1</div>
  <div class="flex-1 bg-green-100 p-6 rounded-lg">Column 2</div>
  <div class="flex-1 bg-yellow-100 p-6 rounded-lg">Column 3</div>
</div>

<!-- Centered flex container with items spaced evenly -->
<div class="flex items-center justify-between px-6 py-4 max-w-7xl mx-auto">
  <div class="text-lg font-bold">Logo</div>
  <nav class="hidden md:flex gap-6">
    <a href="#" class="hover:text-blue-600">Home</a>
    <a href="#" class="hover:text-blue-600">About</a>
    <a href="#" class="hover:text-blue-600">Contact</a>
  </nav>
  <button class="md:hidden p-2">☰</button>
</div>
```

## CSS Grid Layout

```html
<!-- Auto-fill responsive grid with min column width -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-6">
  <div class="bg-white shadow rounded-lg p-4">Card 1</div>
  <div class="bg-white shadow rounded-lg p-4">Card 2</div>
  <div class="bg-white shadow rounded-lg p-4">Card 3</div>
  <div class="bg-white shadow rounded-lg p-4">Card 4</div>
</div>

<!-- Grid with sidebar (2 columns, sidebar spans 1, main spans 3) -->
<div class="grid grid-cols-1 md:grid-cols-4 gap-6 min-h-screen">
  <aside class="md:col-span-1 bg-gray-50 p-4">Sidebar</aside>
  <main class="md:col-span-3 bg-white p-6">Main Content</main>
</div>

<!-- Dashboard grid with spanning -->
<div class="grid grid-cols-12 gap-4 p-4">
  <div class="col-span-12 lg:col-span-3 bg-purple-100 p-4">Stats 1</div>
  <div class="col-span-12 lg:col-span-3 bg-purple-100 p-4">Stats 2</div>
  <div class="col-span-12 lg:col-span-3 bg-purple-100 p-4">Stats 3</div>
  <div class="col-span-12 lg:col-span-3 bg-purple-100 p-4">Stats 4</div>
  <div class="col-span-12 lg:col-span-8 bg-blue-50 p-4">Chart Area</div>
  <div class="col-span-12 lg:col-span-4 bg-green-50 p-4">Activity Feed</div>
</div>
```

## Container & Spacing

```html
<!-- Constrained container with padding -->
<div class="container mx-auto px-4 sm:px-6 lg:px-8">
  <div class="py-8 sm:py-12 lg:py-16">
    <h1 class="text-2xl sm:text-3xl lg:text-4xl font-bold mb-4">Responsive Heading</h1>
    <p class="text-sm sm:text-base lg:text-lg text-gray-600 mb-6">
      Text scales up at sm, lg breakpoints. Spacing grows with screen size.
    </p>
    <div class="space-y-4 sm:space-y-0 sm:flex sm:gap-4">
      <button class="w-full sm:w-auto px-6 py-3 bg-blue-600 text-white rounded-lg">
        Primary Action
      </button>
      <button class="w-full sm:w-auto px-6 py-3 border border-gray-300 rounded-lg">
        Secondary
      </button>
    </div>
  </div>
</div>

<!-- Margin and padding scale -->
<div class="m-2 sm:m-4 md:m-6 lg:m-8 p-4 sm:p-6 lg:p-8 bg-gray-100 rounded-xl">
  <p>Margins and padding grow with breakpoints for consistent white space.</p>
</div>
```

## Breakpoint Reference

```html
<!-- Tailwind breakpoints: sm (640px), md (768px), lg (1024px), xl (1280px), 2xl (1536px) -->
<div class="
  grid
  grid-cols-1          /* mobile: 1 column */
  sm:grid-cols-2       /* sm+: 2 columns */
  md:grid-cols-3       /* md+: 3 columns */
  lg:grid-cols-4       /* lg+: 4 columns */
  xl:grid-cols-5       /* xl+: 5 columns */
  gap-2 sm:gap-4 lg:gap-6
">
  <!-- Items scale gap and columns with breakpoints -->
</div>
```