<template>
  <div class="page">
    <AdminPageHeader title="订单管理" description="查看订单明细，按状态推进接单、制作与交付。">
      <span class="subtle-tag">每 10 秒自动更新</span><button class="btn-ghost" @click="load"><AppIcon name="refresh" :size="15" />刷新订单</button>
    </AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />
    <AdminSummary :loading="loading || (!!loadError && !allOrders.length)" :items="[
      {label:'当前载入订单', value:allOrders.length, note:'最近最多 200 笔'},
      {label:'已付待接单', value:allOrders.filter(o => o.status === 0 && o.payment_status === 1).length, note:'可立即接单处理', warning:true},
      {label:'制作与配送中', value:allOrders.filter(o => o.status === 1 || o.status === 2).length, note:'状态为制作中或配送中'},
      {label:'未支付订单', value:allOrders.filter(o => o.payment_status !== 1 && o.status !== 4).length, note:'在线支付尚未接入'}
    ]" />
    <div class="admin-toolbar"><AppIcon name="search" :size="17" /><input v-model="keyword" class="simple-search" placeholder="搜索订单号、联系人或手机号" aria-label="搜索订单" /><span class="admin-result-count">匹配 {{ filteredOrders.length }} 笔订单</span></div>
    <div class="admin-tab" aria-label="订单状态筛选">
      <button v-for="f in filters" :key="f.label" :class="{ active: currentFilter === f.value }" :aria-pressed="currentFilter === f.value" @click="switchFilter(f.value)">{{ f.label }}<span class="tab-count">{{ f.count }}</span></button>
    </div>
    <div v-if="loading" class="empty-state">正在读取订单…</div>
    <div v-else-if="!loadError && !filteredOrders.length" class="empty-state"><AppIcon name="orders" :size="32" /><strong>暂无{{ filterLabel(currentFilter) }}订单</strong><span>可切换状态或调整搜索关键词</span></div>
    <div v-else class="admin-order-grid">
      <article v-for="o in filteredOrders" :key="o.order_id" class="order-card">
        <div class="order-head"><div><span class="order-no">#{{ o.order_no }}</span><div class="admin-order-meta">{{ o.created_at }}<br />{{ o.contact_name || '未留姓名' }} {{ o.contact_phone }}</div></div><span class="status-badge" :class="`s-${o.status}`">{{ o.status_text }}</span></div>
        <div class="admin-order-location">{{ o.table_no ? `堂食 · ${o.table_no} 桌` : o.delivery_mode === 1 ? '到店自取' : `外卖 · ${o.delivery_address || '未留地址'}` }}</div>
        <div class="admin-order-lines"><div v-for="(item,i) in o.items" :key="i" class="admin-order-line"><span>{{ item.dish_name }}</span><b>× {{ item.quantity }}</b></div></div>
        <div class="order-items">共 {{ o.total_quantity }} 份 · 应付 <b>{{ o.formatted_total }}</b><span class="pay-badge" :class="o.payment_status === 1 ? 'paid' : 'unpaid'" style="margin-left:8px">{{ o.payment_status_text }}<template v-if="o.payment_status === 1 && o.payment_method_text"> · {{ o.payment_method_text }}</template></span></div>
        <div v-if="o.stations?.length" class="admin-order-routing">分单档口 · {{ o.stations.join(' / ') }}</div>
        <div class="order-footer"><span class="admin-order-footer-label">{{ o.status === 4 ? '订单已取消' : o.status === 3 ? '订单已完成' : o.payment_status === 1 ? '按流程处理订单' : '待支付后可接单' }}</span><div><button v-for="step in nextSteps(o)" :key="step.status" class="btn-sm" :class="step.primary ? 'btn-primary' : 'btn-ghost'" :disabled="busyIds.includes(o.order_id)" @click="changeStatus(o.order_id, step.status)">{{ step.label }}</button></div></div>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminSummary from '../components/AdminSummary.vue'
import AppIcon from '../components/AppIcon.vue'

const loadError = ref(''), keyword = ref(''), busyIds = ref([])
let timer
let fetching = false

const allOrders = ref([])
const loading = ref(true)
const currentFilter = ref(null)

const filters = computed(() => {
  const counts = {
    null: allOrders.value.length,
    0: allOrders.value.filter(o => o.status === 0).length,
    1: allOrders.value.filter(o => o.status === 1).length,
    2: allOrders.value.filter(o => o.status === 2).length,
    3: allOrders.value.filter(o => o.status === 3).length,
    4: allOrders.value.filter(o => o.status === 4).length,
  }
  return [
    { label: '全部', value: null, count: counts.null },
    { label: '待接单', value: 0, count: counts[0] },
    { label: '制作中', value: 1, count: counts[1] },
    { label: '配送中', value: 2, count: counts[2] },
    { label: '已完成', value: 3, count: counts[3] },
    { label: '已取消', value: 4, count: counts[4] },
  ]
})

const filteredOrders = computed(() => {
  return allOrders.value.filter(o => (currentFilter.value == null || o.status === currentFilter.value) && (!keyword.value.trim() || `${o.order_no} ${o.contact_name} ${o.contact_phone}`.includes(keyword.value.trim())))
})

function filterLabel(v) {
  return filters.value.find(f => f.value === v)?.label || ''
}

function nextSteps(order) {
  if (order.payment_status !== 1 && order.status !== 0) return []
  switch (order.status) {
    case 0: return order.payment_status === 1 ? [{ label: '接单', status: 1, primary: true }] : [{ label: '取消未支付订单', status: 4 }]
    case 1: return [{ label: order.delivery_mode === 1 ? '自取完成' : '出餐并配送', status: order.delivery_mode === 1 ? 3 : 2, primary: true }]
    case 2: return [{ label: '送达完成', status: 3, primary: true }]
    default: return []
  }
}

async function load() {
  if (fetching) return
  fetching = true
  if (!allOrders.value.length) loading.value = true
  try {
    const res = await adminAPI.orders()
    allOrders.value = res.orders || []
    loadError.value = ''
  } catch (e) {
    loadError.value = e.message + (allOrders.value.length ? '（保留上次成功数据）' : '')
  } finally {
    fetching = false
    loading.value = false
  }
}

async function changeStatus(orderId, status) {
  if (busyIds.value.includes(orderId)) return
  busyIds.value.push(orderId)
  try {
    await adminAPI.updateOrderStatus(orderId, status)
    ElMessage.success('状态已更新')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    busyIds.value = busyIds.value.filter(id => id !== orderId)
  }
}

function switchFilter(v) {
  currentFilter.value = v
}

onMounted(() => { load(); timer = setInterval(load, 10000) })
onUnmounted(() => clearInterval(timer))
</script>
