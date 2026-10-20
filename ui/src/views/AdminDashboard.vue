<template>
  <div class="page dashboard-page">
    <AdminPageHeader title="经营总览" description="掌握今天的经营，也照顾好每一笔待办。" eyebrow="知味 / 今日工作台">
      <button class="btn-ghost" :disabled="loading" @click="load"><AppIcon name="refresh" :size="15" />{{ loading ? '正在更新' : '刷新数据' }}</button>
      <router-link class="btn-primary" to="/admin/orders"><AppIcon name="orders" :size="16" />处理订单</router-link>
    </AdminPageHeader>
    <div class="admin-store-bar">
      <div class="admin-store-identity"><span class="admin-store-mark"><AppIcon name="bowl" :size="25" /></span><div><h2>{{ shop?.name || '餐厅工作空间' }}</h2><p>{{ errors.shop || (shop ? shop.address || '门店地址尚未配置' : '正在读取门店信息') }}</p></div></div>
      <div class="admin-store-meta"><span><AppIcon name="clock" :size="14" />{{ summary?.date || '等待数据' }}</span><router-link to="/" class="text-link">查看顾客点餐页 <AppIcon name="arrow" :size="14" /></router-link></div>
    </div>
    <LoadError :message="errors.summary" @retry="load" />
    <div class="stat-grid" :aria-busy="loading">
      <div v-for="(s, i) in stats" :key="s.label" class="stat-card"><div class="stat-top"><span class="stat-label">{{ s.label }}</span><span class="stat-icon" :class="`tone-${i}`"><AppIcon :name="s.icon" :size="19" /></span></div><div class="stat-value">{{ loading && !summary ? '…' : s.value }}</div><div class="stat-sub">{{ s.note }}</div></div>
    </div>
    <div class="dashboard-main-grid"><section class="card trend-card"><div class="card-header"><div><h2>营业收入趋势</h2><p>最近 7 日 · 优惠后已支付金额</p></div><span class="subtle-tag">近七日</span></div><div class="card-body"><SalesTrend v-if="summary" :points="summary.trend" /><div v-else class="empty-state">{{ loading ? '正在读取经营数据…' : '收入趋势暂不可用' }}</div></div></section>
      <section class="card"><div class="card-header"><div><h2>今日待办</h2><p>关注每一个需要处理的环节</p></div><AppIcon name="clock" :size="19" /></div><div class="todo-list"><router-link to="/admin/orders"><span class="todo-icon"><AppIcon name="orders" /></span><span><strong>待接订单</strong><small>已支付，等待门店接单</small></span><b>{{ summary?.pending_orders ?? '—' }}</b><AppIcon name="chevron" :size="15" /></router-link><router-link to="/admin/inventory"><span class="todo-icon amber"><AppIcon name="box" /></span><span><strong>库存预警</strong><small>{{ errors.inventory ? '库存读取失败，请重试' : '到达补货预警阈值' }}</small></span><b>{{ inventory?.low_count ?? '—' }}</b><AppIcon name="chevron" :size="15" /></router-link><router-link to="/admin/tables"><span class="todo-icon blue"><AppIcon name="table" /></span><span><strong>可用桌台</strong><small>{{ errors.tables ? '桌台读取失败，请重试' : '为下一位客人做好准备' }}</small></span><b>{{ tables?.free ?? '—' }}</b><AppIcon name="chevron" :size="15" /></router-link></div></section></div>
    <div class="dashboard-bottom-grid"><section class="card"><div class="card-header"><div><h2>最近订单</h2><p>最近 {{ recentOrders.length }} 笔 · 按下单时间</p></div><router-link to="/admin/orders" class="text-link">全部订单 <AppIcon name="arrow" :size="15" /></router-link></div><LoadError :message="errors.orders" @retry="load" /><div class="table-scroll" v-if="recentOrders.length"><table class="admin-table"><thead><tr><th>订单 / 时间</th><th>用餐方式</th><th>应付金额</th><th>订单状态</th></tr></thead><tbody><tr v-for="o in recentOrders" :key="o.order_id"><td><strong class="short-order">#{{ o.order_no }}</strong><small class="cell-sub">{{ o.created_at }}</small></td><td>{{ o.table_no ? `${o.table_no} 桌` : o.delivery_mode_text }}</td><td class="amount-cell">{{ o.formatted_total }}<small class="cell-sub">{{ o.payment_status_text }}</small></td><td><span class="status-badge" :class="`s-${o.status}`">{{ o.status_text }}</span></td></tr></tbody></table></div><div v-else-if="!errors.orders" class="empty-state"><AppIcon name="orders" :size="30" /><strong>{{ loading ? '正在读取订单' : '还没有订单记录' }}</strong><span>顾客提交订单后会显示在这里</span></div></section>
      <section class="card"><div class="card-header"><div><h2>常用功能</h2><p>让日常经营更顺手</p></div></div><div class="quick-grid"><router-link v-for="a in actions" :key="a.to" :to="a.to"><span><AppIcon :name="a.icon" :size="24" /></span><strong>{{ a.label }}</strong><small>{{ a.desc }}</small></router-link></div><div class="payment-note"><AppIcon name="money" :size="18" /><span>在线支付尚未接入<br /><small>新订单会保留为待支付</small></span></div></section></div>
    <div class="data-notice"><span class="notice-dot"></span><span>数据来自现有业务库，包含初始化及测试记录；历史支付标记未经支付网关核验。</span><router-link to="/admin/reports">查看统计口径 <AppIcon name="arrow" :size="14" /></router-link></div>
    <p class="last-sync">{{ summary ? `数据更新于 ${summary.generated_at}` : '等待业务数据连接' }} · 页面数据手动刷新</p>
  </div>
</template>
<script setup>
import { computed, ref, onMounted } from 'vue'
import { adminAPI, shopAPI } from '../api'
import AppIcon from '../components/AppIcon.vue'
import LoadError from '../components/LoadError.vue'
import SalesTrend from '../components/SalesTrend.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
const summary = ref(null), inventory = ref(null), tables = ref(null), recentOrders = ref([]), shop = ref(null), loading = ref(false), errors = ref({})
const stats = computed(() => [
  { label: '今日账本收入', value: summary.value?.formatted_revenue ?? '—', note: `已支付 ${summary.value?.paid_orders ?? '—'} 笔 · 排除已取消`, icon: 'money' },
  { label: '今日订单', value: summary.value?.today_orders ?? '—', note: '今日提交的全部订单', icon: 'orders' },
  { label: '平均客单价', value: summary.value?.formatted_avg ?? '—', note: '今日收入 ÷ 今日已支付订单', icon: 'chart' },
  { label: '待接订单', value: summary.value?.pending_orders ?? '—', note: '全部日期 · 已支付待接单', icon: 'clock' },
])
const actions = [{ to: '/admin/menu', icon: 'menu', label: '管理菜品', desc: '上下架与菜品信息' }, { to: '/kitchen', icon: 'chef', label: '后厨工作台', desc: '按档口查看订单' }, { to: '/admin/inventory', icon: 'box', label: '原料补货', desc: '库存与估清管理' }, { to: '/admin/members', icon: 'users', label: '会员管理', desc: '会员信息与优惠券' }]
async function load() {
  if (loading.value) return
  loading.value = true
  const tasks = { summary: [() => adminAPI.reportSummary(), summary], inventory: [() => adminAPI.inventory(), inventory], tables: [() => adminAPI.tables(), tables], orders: [() => adminAPI.orders(), null], shop: [() => shopAPI.info(), shop] }
  await Promise.all(Object.entries(tasks).map(async ([key, [request, target]]) => { try { const result = await request(); if (target) target.value = result; else recentOrders.value = result.orders.slice(0, 5); errors.value[key] = '' } catch(e) { errors.value[key] = e.message + (target?.value || recentOrders.value.length ? '（显示上次成功数据）' : '') } }))
  loading.value = false
}
onMounted(load)
</script>
