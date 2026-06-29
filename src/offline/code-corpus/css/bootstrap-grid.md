---
language: html
tags: [bootstrap, css, grid, responsive]
title: Bootstrap 5 Grid & Components
description: Grid system, containers, breakpoints, utility classes, and common components
source: pattern
---

## Grid System & Containers

```html
<!-- Container types -->
<div class="container">     <!-- Responsive fixed-width (max-width at each breakpoint) --></div>
<div class="container-fluid">   <!-- Full-width always --></div>
<div class="container-sm">    <!-- 100% until sm (576px), then fixed --></div>
<div class="container-md">    <!-- 100% until md (768px), then fixed --></div>
<div class="container-lg">    <!-- 100% until lg (992px), then fixed --></div>
<div class="container-xl">    <!-- 100% until xl (1200px), then fixed --></div>
<div class="container-xxl">   <!-- 100% until xxl (1400px), then fixed --></div>

<!-- Basic responsive grid: 1 col on mobile, 2 on sm, 4 on lg -->
<div class="container">
  <div class="row g-3">  <!-- g-3 adds gap (1rem) between columns -->
    <div class="col-12 col-sm-6 col-lg-3">
      <div class="p-3 bg-light border rounded">Column 1</div>
    </div>
    <div class="col-12 col-sm-6 col-lg-3">
      <div class="p-3 bg-light border rounded">Column 2</div>
    </div>
    <div class="col-12 col-sm-6 col-lg-3">
      <div class="p-3 bg-light border rounded">Column 3</div>
    </div>
    <div class="col-12 col-sm-6 col-lg-3">
      <div class="p-3 bg-light border rounded">Column 4</div>
    </div>
  </div>
</div>
```

## Layout Patterns

```html
<!-- Sidebar + Main layout (2:10 on md, 3:9 on lg) -->
<div class="container">
  <div class="row">
    <div class="col-md-2 col-lg-3 bg-secondary text-white p-3">Sidebar</div>
    <div class="col-md-10 col-lg-9 p-3">Main Content</div>
  </div>
</div>

<!-- Offset columns -->
<div class="container">
  <div class="row justify-content-center">
    <div class="col-md-6 offset-md-3">
      <p>Centered content with offset — takes 6 cols, centered in 12-col grid.</p>
    </div>
  </div>
</div>

<!-- Auto-layout: equal-width columns -->
<div class="container">
  <div class="row">
    <div class="col bg-primary text-white p-3">Auto</div>
    <div class="col bg-info text-white p-3">Auto</div>
    <div class="col bg-warning p-3">Auto</div>
  </div>
</div>

<!-- Nested rows -->
<div class="container">
  <div class="row">
    <div class="col-8 bg-light p-3">
      <div class="row">
        <div class="col-6 bg-white border p-2">Nested 1</div>
        <div class="col-6 bg-white border p-2">Nested 2</div>
      </div>
    </div>
    <div class="col-4 bg-secondary text-white p-3">Sidebar</div>
  </div>
</div>

<!-- Flexbox alignment utilities -->
<div class="container">
  <div class="row align-items-start min-vh-50">    <!-- top, center, bottom, stretch -->
    <div class="col">Aligned top</div>
    <div class="col">Aligned top</div>
  </div>
  <div class="row justify-content-between">         <!-- start, center, end, around, between, evenly -->
    <div class="col-3 bg-light">Left</div>
    <div class="col-3 bg-light">Right</div>
  </div>
</div>
```

## Components: Alerts & Badges

```html
<!-- Alerts with dismiss -->
<div class="alert alert-primary alert-dismissible fade show" role="alert">
  <strong>Primary!</strong> This is a primary alert — check it out!
  <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
</div>

<div class="alert alert-success d-flex align-items-center" role="alert">
  <svg class="bi flex-shrink-0 me-2" width="24" height="24" role="img" aria-label="Success:"><use xlink:href="#check-circle-fill"/></svg>
  <div>Success alert with icon. Also available: <code>alert-danger</code>, <code>alert-warning</code>, <code>alert-info</code>, <code>alert-dark</code>.</div>
</div>

<!-- Badges -->
<h1>Example heading <span class="badge bg-secondary">New</span></h1>
<button type="button" class="btn btn-primary position-relative">
  Notifications <span class="badge bg-danger position-absolute top-0 start-100 translate-middle rounded-pill">99+</span>
</button>

<!-- Badge variants -->
<span class="badge bg-primary">Primary</span>
<span class="badge bg-success">Success</span>
<span class="badge bg-danger">Danger</span>
<span class="badge bg-warning text-dark">Warning</span>
<span class="badge bg-info text-dark">Info</span>
<span class="badge rounded-pill bg-dark">Pill badge</span>
```

## Components: Modal

```html
<!-- Modal trigger -->
<button type="button" class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#exampleModal">
  Launch Modal
</button>

<!-- Modal structure -->
<div class="modal fade" id="exampleModal" tabindex="-1" aria-labelledby="modalLabel" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered modal-lg"> <!-- sizes: sm, lg, xl, fullscreen -->
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="modalLabel">Modal Title</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <p>Modal body content goes here. Supports forms, text, images, etc.</p>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
        <button type="button" class="btn btn-primary">Save changes</button>
      </div>
    </div>
  </div>
</div>
```

## Utility Classes

```html
<!-- Spacing: {property}{sides}-{size} where size is 0-5, auto, or Npx -->
<div class="mt-3 mb-3 p-4 mx-auto">           <!-- margin top/bottom, padding all, margin-x auto -->
<div class="pt-0 pb-2 ps-4 pe-5">             <!-- padding top 0, bottom 2, start 4, end 5 -->
<div class="gap-2 gap-md-4 gap-lg-5">         <!-- gap between flex/grid items -->

<!-- Display -->
<div class="d-none d-md-block">               <!-- hidden on mobile, visible md+ -->
<div class="d-flex d-lg-inline-flex">         <!-- flex on all, inline-flex on lg+ -->
<div class="d-print-none">                    <!-- hidden when printing -->

<!-- Flex utilities -->
<div class="d-flex justify-content-center align-items-center flex-wrap">
<div class="d-flex flex-column flex-md-row">

<!-- Text -->
<p class="text-start text-md-center text-lg-end">Responsive text alignment</p>
<p class="text-truncate" style="max-width: 200px;">This text will be truncated with ellipsis...</p>
<p class="text-uppercase text-muted small">Upper with muted small text</p>

<!-- Colors -->
<div class="text-primary bg-dark border border-danger rounded-3 shadow-sm p-3">

<!-- Width / Height -->
<div class="w-25 w-md-50 w-lg-75">Responsive width</div>
<div class="h-100 min-vh-100">Full viewport height</div>
```

## Breakpoint Reference

```html
<!-- Bootstrap 5 breakpoints:
  xs:  <576px   (default, no prefix)
  sm:  ≥576px
  md:  ≥768px
  lg:  ≥992px
  xl:  ≥1200px
  xxl: ≥1400px
-->
```

## Responsive Navbar

```html
<nav class="navbar navbar-expand-lg navbar-light bg-light">
  <div class="container">
    <a class="navbar-brand" href="#">Brand</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      <ul class="navbar-nav ms-auto">
        <li class="nav-item"><a class="nav-link active" href="#">Home</a></li>
        <li class="nav-item"><a class="nav-link" href="#">Features</a></li>
        <li class="nav-item"><a class="nav-link" href="#">Pricing</a></li>
        <li class="nav-item"><a class="nav-link disabled" href="#" tabindex="-1">Disabled</a></li>
      </ul>
    </div>
  </div>
</nav>
```