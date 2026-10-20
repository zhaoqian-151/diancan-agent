<template>
  <div class="admin-summary" :aria-busy="loading">
    <div v-for="item in items" :key="item.label" class="admin-summary-item" :class="{ 'is-warning': item.warning }">
      <span>{{ item.label }}</span><strong>{{ loading ? '—' : item.value }}</strong><small v-if="item.note">{{ item.note }}</small>
    </div>
  </div>
</template>
<script setup>
defineProps({ items: { type: Array, default: () => [] }, loading: Boolean })
</script>
