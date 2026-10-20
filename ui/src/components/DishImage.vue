<template><div class="dish-visual" :class="{ 'dish-visual-warm': !vegetarian }"><img v-if="safeSrc && !failed" :src="safeSrc" :alt="name" loading="lazy" decoding="async" @error="failed = true" /><span v-if="safeSrc && !failed && safeSrc.startsWith('/images/generated/')" class="ai-image-badge">AI 示意</span><div v-if="!safeSrc || failed" class="dish-placeholder"><AppIcon :name="vegetarian ? 'leaf' : 'bowl'" :size="45" /><span>{{ category || '用心烹饪' }}</span><small>暂未配图</small></div></div></template>
<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
const props = defineProps({ src: String, name: String, category: String, vegetarian: Boolean })
const failed = ref(false)
const safeSrc = computed(() => props.src && !props.src.includes('text_to_image') && (props.src.startsWith('https://') || props.src.startsWith('/images/')) ? props.src : '')
watch(() => props.src, () => { failed.value = false })
</script>
