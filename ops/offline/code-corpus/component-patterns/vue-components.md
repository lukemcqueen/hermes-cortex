---
language: typescript
tags: [vue, components, composition-api]
title: Vue 3 Composition API Components
description: defineProps, defineEmits, slots, provide/inject, composables
source: pattern
---

## Basic Composition API Component

```typescript
<script setup lang="ts">
// Props with type validation
interface UserCardProps {
  name: string;
  email: string;
  avatar?: string;
  role?: 'admin' | 'editor' | 'viewer';
}

const props = withDefaults(defineProps<UserCardProps>(), {
  avatar: '/default-avatar.png',
  role: 'viewer',
});

// Emits with typed payloads
const emit = defineEmits<{
  click: [id: string];
  follow: [userId: string];
  'update:role': [newRole: string];
}>();

function handleClick() {
  emit('click', props.name);
}
</script>

<template>
  <div class="user-card" @click="handleClick">
    <img :src="avatar" :alt="name" class="avatar" />
    <div class="info">
      <h3>{{ name }}</h3>
      <p>{{ email }}</p>
      <span class="badge" :class="role">{{ role }}</span>
    </div>
  </div>
</template>

<style scoped>
.user-card { display: flex; gap: 1rem; padding: 1rem; border: 1px solid #e2e8f0; border-radius: 8px; cursor: pointer; }
.avatar { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; }
.badge { font-size: 0.75rem; padding: 0.125rem 0.5rem; border-radius: 999px; }
.admin { background: #fef3c7; color: #92400e; }
.editor { background: #dbeafe; color: #1e40af; }
.viewer { background: #f3f4f6; color: #374151; }
</style>
```

## Slots (Named and Scoped)

```typescript
<script setup lang="ts">
interface DataTableProps<T> {
  items: T[];
  loading?: boolean;
}

defineProps<DataTableProps<any>>();
</script>

<template>
  <div class="data-table">
    <div v-if="loading" class="loading-state">
      <slot name="loading">
        <p>Loading data...</p>
      </slot>
    </div>

    <template v-else-if="items.length === 0">
      <slot name="empty">
        <p>No items to display.</p>
      </slot>
    </template>

    <table v-else>
      <thead>
        <slot name="header">
          <tr>
            <th v-for="(_, key) in items[0]" :key="String(key)">{{ key }}</th>
          </tr>
        </slot>
      </thead>
      <tbody>
        <tr v-for="(item, index) in items" :key="index">
          <!-- Scoped slot: passes item data back to parent -->
          <slot name="row" :item="item" :index="index">
            <td v-for="(value, key) in item" :key="String(key)">{{ value }}</td>
          </slot>
        </tr>
      </tbody>
    </table>

    <div class="footer">
      <slot name="footer" :count="items.length">
        <small>{{ items.length }} total rows</small>
      </slot>
    </div>
  </div>
</template>

<!-- Usage -->
<DataTable :items="users" :loading="isLoading">
  <template #loading>
    <SkeletonLoader />
  </template>
  <template #row="{ item }">
    <td>{{ item.name }}</td>
    <td>{{ item.email }}</td>
    <td><button @click="edit(item.id)">Edit</button></td>
  </template>
  <template #footer="{ count }">
    <Pagination :total="count" />
  </template>
</DataTable>
```

## Provide / Inject

```typescript
<script setup lang="ts">
import { provide, ref, readonly, type Ref } from 'vue';

/* ---------- Provider ---------- */
interface ThemeConfig {
  primaryColor: string;
  spacing: 'compact' | 'comfortable' | 'spacious';
  darkMode: boolean;
}

const theme = ref<ThemeConfig>({
  primaryColor: '#3b82f6',
  spacing: 'comfortable',
  darkMode: false,
});

function toggleDarkMode() {
  theme.value.darkMode = !theme.value.darkMode;
}

function setSpacing(spacing: ThemeConfig['spacing']) {
  theme.value.spacing = spacing;
}

// Provide both the reactive value and updater functions
provide('theme', readonly(theme)); // readonly prevents child mutation
provide('themeActions', { toggleDarkMode, setSpacing });
</script>

<template>
  <div :class="['app', { dark: theme.darkMode }]">
    <slot />
  </div>
</template>
```

```typescript
<script setup lang="ts">
import { inject } from 'vue';

/* ---------- Consumer ---------- */
interface ThemeConfig {
  primaryColor: string;
  spacing: 'compact' | 'comfortable' | 'spacious';
  darkMode: boolean;
}

interface ThemeActions {
  toggleDarkMode: () => void;
  setSpacing: (spacing: ThemeConfig['spacing']) => void;
}

const theme = inject<Readonly<ThemeConfig>>('theme');
const actions = inject<ThemeActions>('themeActions');

if (!theme || !actions) {
  throw new Error('ThemeProvider is required as a parent component');
}
</script>

<template>
  <div :style="{ '--primary': theme.primaryColor, padding: theme.spacing === 'compact' ? '0.5rem' : '1rem' }">
    <button @click="actions.toggleDarkMode">
      Toggle {{ theme.darkMode ? 'Light' : 'Dark' }}
    </button>
    <slot />
  </div>
</template>
```

## Composables (Vue 3 Equivalent of Hooks)

```typescript
// composables/useMediaQuery.ts
import { ref, onMounted, onUnmounted } from 'vue';

export function useMediaQuery(query: string) {
  const matches = ref(false);

  let mql: MediaQueryList | null = null;
  const handler = (e: MediaQueryListEvent) => {
    matches.value = e.matches;
  };

  onMounted(() => {
    mql = window.matchMedia(query);
    matches.value = mql.matches;
    mql.addEventListener('change', handler);
  });

  onUnmounted(() => {
    mql?.removeEventListener('change', handler);
  });

  return { matches };
}
```

```typescript
// composables/useDebounce.ts
import { ref, watch, type Ref } from 'vue';

export function useDebounce<T>(source: Ref<T>, delayMs: number = 300) {
  const debounced = ref(source.value) as Ref<T>;
  let timer: ReturnType<typeof setTimeout> | null = null;

  watch(source, (newVal) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      debounced.value = newVal;
    }, delayMs);
  });

  return { debounced };
}
```

```typescript
// composables/usePagination.ts
import { ref, computed } from 'vue';

export function usePagination<T>(items: Ref<T[]>, pageSize: number) {
  const currentPage = ref(1);

  const totalPages = computed(() => Math.max(1, Math.ceil(items.value.length / pageSize)));

  const paginatedItems = computed(() => {
    const start = (currentPage.value - 1) * pageSize;
    return items.value.slice(start, start + pageSize);
  });

  function goToPage(page: number) {
    currentPage.value = Math.max(1, Math.min(page, totalPages.value));
  }

  function nextPage() {
    goToPage(currentPage.value + 1);
  }

  function prevPage() {
    goToPage(currentPage.value - 1);
  }

  return { currentPage, totalPages, paginatedItems, goToPage, nextPage, prevPage };
}
```

```typescript
// Usage in a component
<script setup lang="ts">
import { ref } from 'vue';
import { useMediaQuery } from './composables/useMediaQuery';
import { useDebounce } from './composables/useDebounce';
import { usePagination } from './composables/usePagination';

const searchQuery = ref('');
const { debounced: debouncedSearch } = useDebounce(searchQuery);
const { matches: isDesktop } = useMediaQuery('(min-width: 1024px)');

const allItems = ref([
  { id: 1, name: 'Alpha' },
  { id: 2, name: 'Beta' },
  { id: 3, name: 'Gamma' },
  { id: 4, name: 'Delta' },
  { id: 5, name: 'Epsilon' },
]);

const { currentPage, totalPages, paginatedItems, nextPage, prevPage } = usePagination(allItems, 2);
</script>

<template>
  <div :class="{ desktop: isDesktop }">
    <input v-model="searchQuery" placeholder="Search..." />
    <p v-if="debouncedSearch">Debounced: {{ debouncedSearch }}</p>

    <div v-for="item in paginatedItems" :key="item.id">
      {{ item.name }}
    </div>

    <div v-if="totalPages > 1">
      <button :disabled="currentPage <= 1" @click="prevPage">Prev</button>
      <span>{{ currentPage }} / {{ totalPages }}</span>
      <button :disabled="currentPage >= totalPages" @click="nextPage">Next</button>
    </div>
  </div>
</template>
```