<template>
  <div class="page">
    <AdminPageHeader title="后厨工作台" description="按档口组织制作，让每一份出餐都有清晰进度。"><span class="subtle-tag">每 5 秒自动更新</span><button class="btn-ghost" @click="load"><AppIcon name="refresh" :size="15" />刷新看板</button></AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />
    <div class="admin-kitchen-status"><AppIcon name="chef" :size="24" /><span>待处理 <strong>{{ loading || updatedAt === '—' ? '—' : data.total_orders }}</strong> 单</span><span>共 <strong>{{ loading || updatedAt === '—' ? '—' : data.total_quantity }}</strong> 份菜品</span><span class="admin-result-count">更新于 {{ updatedAt }} · 仅显示已支付待接 / 制作中订单</span></div>
    <div v-if="loading" class="empty-state">正在读取后厨订单…</div>
    <div v-else class="kitchen-grid"><section v-for="s in data.stations" :key="s.station" class="kitchen-col">
      <div class="kitchen-col-head"><span class="admin-station-title"><AppIcon :name="s.station.includes('凉菜') ? 'leaf' : s.station.includes('饮品') ? 'bowl' : 'chef'" :size="19" />{{ s.station }}</span><span class="kitchen-count">{{ s.orders.length }} 单 / {{ s.total_quantity }} 份</span></div>
      <div class="kitchen-col-body"><article v-for="o in s.orders" :key="o.order_id" class="kitchen-card"><div class="kitchen-card-head"><span class="kitchen-table">{{ o.table_no ? `${o.table_no} 桌` : o.delivery_mode === 1 ? '到店自取' : '外卖' }}</span><span class="kitchen-time">{{ elapsed(o.created_at) }}</span></div><div class="kitchen-order-no">#{{ o.order_no }}</div><ul class="kitchen-items"><li v-for="(it,i) in o.items" :key="i"><span class="kitchen-qty">×{{ it.quantity }}</span> {{ it.dish_name }}</li></ul><div class="kitchen-card-foot"><span class="status-badge" :class="`s-${o.status}`">{{ o.status_text }}</span><button class="btn-sm btn-primary" :disabled="busyIds.includes(o.order_id)" @click="advance(o, o.status === 0 ? 1 : o.delivery_mode === 2 ? 2 : 3)">{{ o.status === 0 ? '接单制作' : '出餐完成' }}</button></div></article><div v-if="!s.orders.length" class="empty-state"><AppIcon name="chef" :size="30" /><strong>当前档口暂无待办</strong><small>新订单分配后会自动显示在这里</small></div></div>
    </section></div>
    <p v-if="!loading && !loadError && !data.total_orders" class="admin-inline-note">当前没有待处理订单，档口看板保持就绪。</p>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AppIcon from '../components/AppIcon.vue'
const loadError = ref(''), busyIds = ref([])
let fetching = false

const data = ref({ stations: [], total_orders: 0, total_quantity: 0 })
const loading = ref(true)
const updatedAt = ref('—')
let timer = null

function elapsed(createdAt) {
  const t = new Date((createdAt || '').replace(/-/g, '/')).getTime()
  if (!t) return ''
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  return `${Math.floor(mins / 60)} 小时前`
}

async function load() {
  if (fetching) return
  fetching = true
  try {
    data.value = await adminAPI.kitchen()
    loadError.value = ''
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (e) {
    loadError.value = e.message + (updatedAt.value !== '—' ? '（保留上次成功数据）' : '')
  } finally {
    fetching = false
    loading.value = false
  }
}

async function advance(order, status) {
  if (busyIds.value.includes(order.order_id)) return
  busyIds.value.push(order.order_id)
  try {
    await adminAPI.updateOrderStatus(order.order_id, status)
    ElMessage.success('已更新')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    busyIds.value = busyIds.value.filter(id => id !== order.order_id)
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>
