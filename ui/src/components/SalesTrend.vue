<template>
  <div class="trend-chart" v-if="points.length"><div class="chart-y"><span>¥{{ ceiling.toFixed(0) }}</span><span>¥{{ (ceiling / 2).toFixed(0) }}</span><span>¥0</span></div><div class="chart-plot"><svg viewBox="0 0 600 180" preserveAspectRatio="none" role="img" :aria-label="'最近七日收入：' + points.map(p => `${p.date} ${p.revenue}元`).join('，')"><defs><linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2d785b" stop-opacity=".2" /><stop offset="100%" stop-color="#2d785b" stop-opacity="0" /></linearGradient></defs><path d="M0 10H600 M0 90H600 M0 170H600" stroke="#e9ede9" stroke-dasharray="4 5" /><path :d="area" fill="url(#chart-area)" /><path :d="line" fill="none" stroke="#28694e" stroke-width="2.5" vector-effect="non-scaling-stroke" /><circle v-for="(p, i) in points" :key="p.date" :cx="x(i)" :cy="y(p.revenue)" r="4" fill="#fff" stroke="#28694e" stroke-width="2"><title>{{ p.date }} · ¥{{ p.revenue.toFixed(2) }} · {{ p.paid_orders }} 单</title></circle></svg><div class="chart-x"><span v-for="p in points" :key="p.date">{{ p.date.slice(5).replace('-', '/') }}</span></div></div></div>
  <p class="muted chart-caption">{{ points.some(p => p.revenue > 0) ? '按支付日期汇总，鼠标移至节点查看金额。' : '最近七日暂无符合统计口径的收入记录。' }}</p>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ points: { type: Array, default: () => [] } })
const ceiling = computed(() => Math.max(100, ...props.points.map(p => Math.ceil(p.revenue / 100) * 100)))
const x = i => 12 + i * (576 / Math.max(props.points.length - 1, 1))
const y = v => 170 - v / ceiling.value * 160
const line = computed(() => props.points.map((p, i) => `${i ? 'L' : 'M'}${x(i)} ${y(p.revenue)}`).join(' '))
const area = computed(() => `${line.value} L${x(props.points.length - 1)} 170 L12 170 Z`)
</script>
