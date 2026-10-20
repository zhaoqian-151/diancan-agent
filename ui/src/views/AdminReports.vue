<template>
  <div class="page">
    <AdminPageHeader title="经营报表" description="用真实订单回看收入、菜品表现与经营构成。"><button class="btn-ghost" :disabled="loading" @click="load"><AppIcon name="refresh" :size="15" />刷新报表</button></AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />

    <div v-if="loading" class="empty-state">
      <div>正在读取经营报表…</div>
    </div>

    <template v-else-if="summary">
      <div class="admin-report-period"><strong>今日经营快照 · {{ summary.date }}</strong><span>更新于 {{ summary.generated_at }}</span></div>
      <!-- 核心指标 -->
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">今日账本收入</span><span class="stat-icon tone-0"><AppIcon name="money" :size="19" /></span></div>
          <div class="stat-value">{{ summary.formatted_revenue }}</div>
          <div class="stat-sub">已支付 {{ summary.paid_orders }} 单</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">今日订单量</span><span class="stat-icon tone-1"><AppIcon name="orders" :size="19" /></span></div>
          <div class="stat-value">{{ summary.today_orders }}</div>
          <div class="stat-sub">{{ summary.date }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">客单价</span><span class="stat-icon tone-2"><AppIcon name="chart" :size="19" /></span></div>
          <div class="stat-value">{{ summary.formatted_avg }}</div>
          <div class="stat-sub">营业额 / 已支付订单</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-label">热销菜品</span><span class="stat-icon tone-3"><AppIcon name="menu" :size="19" /></span></div>
          <div class="stat-value report-top-dish">{{ summary.top_dishes[0]?.dish_name || '—' }}</div>
          <div class="stat-sub">
            <template v-if="summary.top_dishes[0]">
              已售 {{ summary.top_dishes[0].quantity }} 份
            </template>
            <template v-else>暂无销售数据</template>
          </div>
        </div>
      </div>
      <section class="card" style="margin-bottom:22px"><div class="card-header"><div><h2>最近七日收入</h2><p>优惠后已支付金额 · 排除取消订单</p></div><span class="subtle-tag">近七日</span></div><div class="card-body"><SalesTrend :points="summary.trend" /></div></section>

      <div class="report-cols">
        <!-- 热销 TOP5 -->
        <div class="card">
          <div class="card-header"><div><h2>热销菜品 TOP 5</h2><p>今日已支付订单 · 优惠前金额</p></div><AppIcon name="menu" :size="19" /></div>
          <div class="card-body">
            <div v-if="summary.top_dishes.length === 0" class="empty-state" style="padding:24px">
              <AppIcon name="menu" :size="27" /><strong>今日暂无菜品销售记录</strong><small>产生已支付订单后显示真实排行</small>
            </div>
            <div v-for="(d, i) in summary.top_dishes" :key="d.dish_name" class="rank-row">
              <span class="rank-no">{{ i + 1 }}</span>
              <span class="rank-name">{{ d.dish_name }}</span>
              <span style="color:#6b7280;font-size:13px">×{{ d.quantity }}</span>
              <span class="rank-amount">{{ d.formatted_amount }}</span>
            </div>
          </div>
        </div>

        <!-- 分类占比 -->
        <div class="card">
          <div class="card-header"><div><h2>分类销售构成</h2><p>今日已支付订单 · 优惠前金额</p></div><AppIcon name="chart" :size="19" /></div>
          <div class="card-body">
            <div v-if="summary.category_ratio.length === 0" class="empty-state" style="padding:24px">
              <AppIcon name="chart" :size="27" /><strong>今日暂无分类销售记录</strong><small>有实际销售后显示分类占比</small>
            </div>
            <div v-for="c in summary.category_ratio" :key="c.category" class="ratio-row">
              <div class="ratio-head">
                <span>{{ c.category }}</span>
                <span>{{ c.formatted_amount }} · {{ c.ratio }}%</span>
              </div>
              <div class="ratio-bar">
                <div class="ratio-fill" :style="{ width: c.ratio + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 订单状态分布 -->
      <div class="card" style="margin-top:16px">
        <div class="card-header"><div><h2>订单状态分布</h2><p>按今日下单时间统计 · 含未支付订单</p></div></div>
        <div class="card-body" style="display:flex;gap:28px;flex-wrap:wrap">
          <span v-if="!summary.status_distribution.length" class="muted">今日还没有提交订单</span>
          <div v-for="s in summary.status_distribution" :key="s.status">
            <span class="status-badge" :class="`s-${s.status}`">{{ s.status_text }}</span>
            <span style="margin-left:8px;font-weight:700">{{ s.count }}</span>
          </div>
        </div>
      </div>
      <div class="data-notice"><span>{{ summary.source }}<br />{{ summary.scope }}</span></div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import SalesTrend from '../components/SalesTrend.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AppIcon from '../components/AppIcon.vue'
const loadError = ref('')

const summary = ref(null)
const loading = ref(true)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    summary.value = await adminAPI.reportSummary()
  } catch (e) {
    loadError.value = e.message + (summary.value ? '（下方保留上次成功数据）' : '')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
