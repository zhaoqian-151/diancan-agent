<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.grid" /></svg></template>
<script setup>
defineProps({ name: String, size: { type: [Number, String], default: 20 } })
const paths = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  bowl: 'M3 11h18c0 6-4 9-9 9s-9-3-9-9z M7 4v3 M12 3v4 M17 4v3 M7 21h10',
  orders: 'M6 3h12v18l-3-2-3 2-3-2-3 2z M9 7h6 M9 11h6 M9 15h3',
  chart: 'M4 3v17h17 M8 16v-4 M13 16V8 M18 16V5',
  menu: 'M4 4h6v7H4z M14 4h6v7h-6z M4 15h6v5H4z M14 15h6v5h-6z',
  table: 'M3 9h18v5H3z M5 14v7 M19 14v7 M8 3v6 M16 3v6',
  box: 'm12 3 9 5v9l-9 5-9-5V8z m-9 5 9 5 9-5 M12 13v9 M7 5l9 5',
  users: 'M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2 M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M20 21v-2a4 4 0 0 0-3-4 M16 3a4 4 0 0 1 0 8',
  chef: 'M6 14a5 5 0 0 1-1-10 6 6 0 0 1 11 0 5 5 0 0 1 2 10v7H6z M6 17h12',
  arrow: 'M5 12h14 M14 7l5 5-5 5', search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 3 M18 18A8 8 0 0 1 5 15',
  clock: 'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0z M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  cart: 'M3 3h2l3 13h11l2-9H6 M9 21h.01 M18 21h.01',
  money: 'M3 5h18v14H3z M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M6 8h.01 M18 16h.01',
  chevron: 'm9 5 7 7-7 7', bars: 'M4 6h16 M4 12h16 M4 18h16', leaf: 'M20 3C7 3 2 8 5 16s15 4 15-13z M5 20 15 10',
}
</script>
