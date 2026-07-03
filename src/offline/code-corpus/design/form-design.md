---
language: html
tags: [forms, ux, validation, design]
title: Form UX & Design Patterns
description: Label placement, validation feedback, error states, autocomplete, input types, progressive enhancement
source: pattern
---

## Label Placement & Structure

```html
<!-- Top-aligned labels (recommended — best scanability, widest support) -->
<form class="max-w-md mx-auto space-y-6">
  <div class="form-group">
    <label for="full-name" class="block text-sm font-medium text-gray-700 mb-1">
      Full Name
    </label>
    <input
      id="full-name"
      type="text"
      class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      autocomplete="name"
      aria-required="true"
    >
  </div>

  <!-- Floating label pattern (visually compact, slightly harder to scan) -->
  <div class="relative">
    <input
      id="email"
      type="email"
      class="peer w-full px-4 pt-6 pb-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      placeholder=" "
      autocomplete="email"
    >
    <label
      for="email"
      class="absolute left-4 top-4 text-gray-500 text-sm transition-all peer-placeholder-shown:top-4 peer-placeholder-shown:text-base peer-focus:top-1 peer-focus:text-xs peer-focus:text-blue-600"
    >
      Email Address
    </label>
  </div>

  <!-- Inline label (for simple forms, short inputs) -->
  <div class="flex items-center gap-3">
    <label for="quantity" class="text-sm font-medium text-gray-700 whitespace-nowrap">
      Qty:
    </label>
    <input
      id="quantity"
      type="number"
      min="1"
      max="99"
      class="w-20 px-3 py-2 border border-gray-300 rounded-lg"
    >
  </div>
</form>
```

## Input Types & Autocomplete

```html
<form class="max-w-md mx-auto space-y-4">
  <!-- Use correct type for mobile keyboard optimization -->
  <div>
    <label for="email">Email</label>
    <input id="email" type="email" autocomplete="email" inputmode="email">
  </div>

  <div>
    <label for="phone">Phone</label>
    <input id="phone" type="tel" autocomplete="tel" inputmode="tel">
  </div>

  <div>
    <label for="url">Website</label>
    <input id="url" type="url" autocomplete="url" inputmode="url">
  </div>

  <div>
    <label for="search">Search</label>
    <input id="search" type="search" autocomplete="search" inputmode="search">
  </div>

  <div>
    <label for="number">Quantity</label>
    <input id="number" type="number" min="1" max="100" step="1" inputmode="numeric">
  </div>

  <div>
    <label for="credit">Card Number</label>
    <input id="credit" type="text" autocomplete="cc-number" inputmode="numeric" pattern="[0-9]{13,19}">
  </div>

  <div>
    <label for="date">Date</label>
    <input id="date" type="date" min="2026-01-01" max="2027-12-31">
  </div>

  <div>
    <label for="password">Password</label>
    <input id="password" type="password" autocomplete="current-password" minlength="8">
  </div>

  <!-- Full list of autocomplete values -->
  <!-- name, given-name, family-name, email, tel, street-address, address-line1,
       address-line2, address-level2 (city), address-level1 (state), postal-code,
       country-name, cc-number, cc-exp, cc-csc, cc-name, username, new-password,
       current-password, organization, url, photo, tel-national, bday, transaction-currency -->
</form>
```

## Validation Feedback & Error States

```html
<form class="max-w-md mx-auto space-y-6" novalidate>
  <!-- Success state -->
  <div>
    <label for="valid-field" class="block text-sm font-medium text-gray-700 mb-1">
      Email (valid)
    </label>
    <input
      id="valid-field"
      type="email"
      value="user@example.com"
      class="w-full px-4 py-2.5 border-2 border-green-500 bg-green-50 rounded-lg text-green-900 focus:ring-2 focus:ring-green-500 outline-none"
      aria-describedby="valid-feedback"
    >
    <p id="valid-feedback" class="mt-1 text-sm text-green-600 flex items-center gap-1">
      ✓ Email looks good!
    </p>
  </div>

  <!-- Error state with inline message -->
  <div>
    <label for="invalid-field" class="block text-sm font-medium text-red-700 mb-1">
      Email
    </label>
    <input
      id="invalid-field"
      type="email"
      value="invalid-email"
      class="w-full px-4 py-2.5 border-2 border-red-500 bg-red-50 rounded-lg text-red-900 focus:ring-2 focus:ring-red-500 outline-none"
      aria-invalid="true"
      aria-describedby="error-feedback"
    >
    <p id="error-feedback" class="mt-1 text-sm text-red-600 flex items-center gap-1" role="alert">
      ✗ Please enter a valid email address.
    </p>
  </div>

  <!-- Warning / suggestion -->
  <div>
    <label for="username" class="block text-sm font-medium text-gray-700 mb-1">
      Username
    </label>
    <div class="relative">
      <input
        id="username"
        type="text"
        value="johndoe"
        class="w-full px-4 py-2.5 border-2 border-yellow-400 bg-yellow-50 rounded-lg focus:ring-2 focus:ring-yellow-400 outline-none"
      >
    </div>
    <p class="mt-1 text-sm text-yellow-700 flex items-center gap-1">
      ⚠ Username "johndoe" is taken. Try "johndoe123".
    </p>
  </div>

  <!-- Error summary at top of form -->
  <div
    role="alert"
    class="p-4 bg-red-50 border border-red-200 rounded-lg"
    tabindex="-1"
  >
    <h2 class="text-sm font-semibold text-red-800 mb-2">
      Please fix the following errors:
    </h2>
    <ul class="list-disc list-inside text-sm text-red-700 space-y-1">
      <li><a href="#full-name" class="underline hover:no-underline">Full name is required</a></li>
      <li><a href="#email" class="underline hover:no-underline">Email is invalid</a></li>
      <li><a href="#password" class="underline hover:no-underline">Password must be at least 8 characters</a></li>
    </ul>
  </div>
</form>
```

## Progressive Enhancement

```html
<form
  class="max-w-md mx-auto space-y-6"
  action="/submit"
  method="POST"
>
  <!-- Always start with a working HTML form (no JS required) -->

  <div>
    <label for="name">Name</label>
    <input id="name" name="name" type="text" required>
  </div>

  <div>
    <label for="message">Message</label>
    <textarea id="message" name="message" rows="4" required></textarea>
  </div>

  <!-- Native validation works without JS -->
  <button type="submit" class="px-6 py-2.5 bg-blue-600 text-white rounded-lg">
    Submit
  </button>

  <!-- Enhanced with JS: real-time validation, async submit, etc. -->
  <script type="module">
    const form = document.querySelector('form');
    const inputs = form.querySelectorAll('input, textarea');

    // Real-time validation on blur
    inputs.forEach(input => {
      input.addEventListener('blur', () => {
        validateField(input);
      });

      input.addEventListener('input', () => {
        // Clear error state while typing
        if (input.dataset.wasInvalid) {
          clearError(input);
        }
      });
    });

    // Form-level validation
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const isValid = [...inputs].every(input => validateField(input));

      if (!isValid) {
        // Focus first error
        const firstError = form.querySelector('[aria-invalid="true"]');
        firstError?.focus();
        return;
      }

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          headers: { 'Accept': 'application/json' }
        });

        if (response.ok) {
          showSuccess(form);
        } else {
          showServerError(form, await response.json());
        }
      } catch (err) {
        showNetworkError(form);
      }
    });

    function validateField(input) {
      if (input.validity.valid) {
        clearError(input);
        return true;
      }
      showError(input, getErrorMessage(input));
      return false;
    }

    function showError(input, message) {
      input.setAttribute('aria-invalid', 'true');
      input.dataset.wasInvalid = 'true';
      // Show error message element
      const errorEl = input.parentElement.querySelector('.error-message');
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.hidden = false;
      }
    }

    function clearError(input) {
      input.removeAttribute('aria-invalid');
      delete input.dataset.wasInvalid;
      const errorEl = input.parentElement.querySelector('.error-message');
      if (errorEl) {
        errorEl.hidden = true;
      }
    }

    function getErrorMessage(input) {
      if (input.validity.valueMissing) return 'This field is required.';
      if (input.validity.typeMismatch) return `Please enter a valid ${input.type}.`;
      if (input.validity.tooShort) return `Minimum ${input.minLength} characters.`;
      return 'Please check this field.';
    }
  </script>
</form>
```

## Form Layout Patterns

```html
<!-- Two-column layout for address forms -->
<form class="max-w-2xl mx-auto">
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div>
      <label for="first-name">First Name</label>
      <input id="first-name" type="text" autocomplete="given-name">
    </div>
    <div>
      <label for="last-name">Last Name</label>
      <input id="last-name" type="text" autocomplete="family-name">
    </div>
  </div>

  <div>
    <label for="address">Street Address</label>
    <input id="address" type="text" autocomplete="street-address">
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div>
      <label for="city">City</label>
      <input id="city" type="text" autocomplete="address-level2">
    </div>
    <div>
      <label for="state">State</label>
      <select id="state" autocomplete="address-level1">
        <option value="">Select...</option>
        <option value="CA">California</option>
        <option value="NY">New York</option>
      </select>
    </div>
    <div>
      <label for="zip">ZIP Code</label>
      <input id="zip" type="text" autocomplete="postal-code" pattern="[0-9]{5}">
    </div>
  </div>
</form>
```