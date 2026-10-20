<template>
  <div class="page">
    <h1 class="page-title">我的订单</h1>
    <div class="payment-note"><span>在线支付尚未接入，待支付订单请联系门店确认收款方式。历史支付状态为本地账本记录。</span></div>
    <LoadError :message="loadError" @retry="load" />

    <div v-if="loading" class="empty-state">
      <div class="emoji">⏳</div><div>加载中...</div>
    </div>

    <div v-else-if="!loadError && orders.length === 0" class="empty-state">
      <div class="emoji">📋</div><div>还没有订单</div>
      <router-link to="/" class="btn-primary" style="margin-top:16px">去点餐</router-link>
    </div>

    <div v-else>
      <div v-for="o in orders" :key="o.order_id" class="order-card">
        <div class="order-head">
          <div>
            <span class="order-no">#{{ o.order_no }}</span>
            <div style="font-size:13px;color:#6b7280;margin-top:4px">{{ o.created_at }}</div>
          </div>
          <span class="status-badge" :class="`s-${o.status}`">{{ o.status_text }}</span>
        </div>
        <div class="order-items">
          {{ o.delivery_mode === 1 ? '到店自取' : `送到：${o.delivery_address || '—'}` }}
        </div>
        <div class="order-line-detail" v-for="item in o.items" :key="item.dish_id">{{ item.dish_name }} × {{ item.quantity }}<span>¥{{ item.subtotal.toFixed(2) }}</span></div>
        <div class="order-footer">
          <span style="color:#6b7280">{{ o.contact_name }} {{ o.contact_phone }}</span>
          <span class="order-total"><small>{{ o.payment_status === 1 ? '账本已付' : '应付' }} </small>{{ o.formatted_total }}</span>
        </div>
        <div class="order-pay-row">
          <span
            class="pay-badge"
            :class="o.payment_status === 1 ? 'paid' : 'unpaid'"
          >
            {{ o.payment_status_text }}
            <template v-if="o.payment_status === 1 && o.payment_method_text">
              · {{ o.payment_method_text }}
            </template>
          </span>
          <span class="muted" v-if="o.payment_status !== 1 && o.status !== 4">请联系门店处理支付</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { orderAPI } from '../api'
import LoadError from '../components/LoadError.vue'
const loadError = ref('')

const orders = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await orderAPI.list(50)
    orders.value = res.orders || []
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
