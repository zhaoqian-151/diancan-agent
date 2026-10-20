<template>
  <div class="admin-page-heading">
    <div><div class="admin-eyebrow">{{ eyebrow }}</div><h1>{{ title }}</h1><p>{{ description }}</p></div>
    <div class="admin-heading-actions"><slot /></div>
  </div>
</template>
<script setup>
defineProps({ title: String, description: String, eyebrow: { type: String, default: '知味 / 餐厅经营' } })
</script>
