<template><div v-if="message" class="load-error" role="alert"><div><strong>暂时无法获取数据</strong><p>{{ message }}</p></div><button class="btn-ghost btn-sm" @click="$emit('retry')">重新加载</button></div></template>
<script setup>defineProps({ message: String }); defineEmits(['retry'])</script>
