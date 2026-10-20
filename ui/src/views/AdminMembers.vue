<template>
  <div class="page">
    <AdminPageHeader title="会员管理" description="维护熟客关系，清楚记录余额、积分与优惠券。"><button class="btn-primary" @click="openCreate">＋ 新增会员</button></AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />
    <AdminSummary :loading="loading || (!!loadError && !members.length)" :items="[
      {label:'当前结果会员', value:members.length, note:keyword ? '按搜索条件统计' : '当前载入会员'},
      {label:'账本余额合计', value:`¥${members.reduce((n,m) => n + Number(m.balance || 0),0).toFixed(2)}`, note:'仅统计当前搜索结果'},
      {label:'可用优惠券', value:members.reduce((n,m) => n + Number(m.coupon_count || 0),0), note:'当前结果会员持有券数'},
      {label:'积分合计', value:members.reduce((n,m) => n + Number(m.points || 0),0), note:'仅统计当前搜索结果'}
    ]" />
    <div class="admin-toolbar"><div class="member-toolbar"><el-input v-model="keyword" placeholder="手机号 / 姓名" clearable aria-label="搜索会员" @keyup.enter="load" @clear="load" /><button class="btn-ghost" :disabled="loading" @click="load"><AppIcon name="search" :size="15" />搜索会员</button><span class="admin-result-count">{{ members.length }} 位会员</span></div></div>
    <div class="payment-note">余额为本地会员账本。充值仅登记账本金额，请先核对实际收款；不会发起在线扣款。</div>
    <div v-if="loading" class="empty-state">正在读取会员…</div>
    <div v-else-if="!loadError && !members.length" class="empty-state"><AppIcon name="users" :size="32" /><strong>{{ keyword ? '没有符合搜索条件的会员' : '还没有会员' }}</strong><span>可调整搜索条件或新增会员</span></div>
    <div v-else class="member-grid" style="margin-top:20px"><article v-for="m in members" :key="m.id" class="member-card">
      <div class="member-card-head"><span class="admin-member-avatar">{{ (m.name || '客').slice(0,1) }}</span><div><div class="admin-member-name">{{ m.name || '未填写姓名' }}</div><span class="member-phone">{{ m.phone }}</span></div><span class="member-level">{{ m.level_text }}</span></div>
      <div class="admin-member-balance-label">会员账本余额</div><div class="member-balance">¥{{ Number(m.balance).toFixed(2) }}</div><div class="member-meta">{{ m.points }} 积分 <span style="margin:0 10px">/</span> {{ m.coupon_count }} 张可用优惠券</div>
      <div class="admin-member-actions"><button class="btn-sm btn-primary" @click="openRecharge(m)">登记充值</button><button class="btn-sm btn-ghost" @click="openCoupon(m)">发券</button><button class="btn-sm btn-ghost" @click="viewCoupons(m)">券明细</button></div>
    </article></div>

    <!-- 新增会员 -->
    <el-dialog v-model="createVisible" title="新增会员" width="380px">
      <el-form label-width="70px">
        <el-form-item label="手机号">
          <el-input v-model="form.phone" maxlength="11" placeholder="11 位手机号" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.name" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">注册</el-button>
      </template>
    </el-dialog>

    <!-- 充值 -->
    <el-dialog v-model="rechargeVisible" title="会员充值" width="380px">
      <p style="margin:0 0 10px;font-size:14px;color:#4b5563">
        为 <b>{{ current?.phone }}</b> 充值（当前余额 ¥{{ Number(current?.balance || 0).toFixed(2) }}）
      </p>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <el-button v-for="a in quickAmounts" :key="a" @click="amount = a">¥{{ a }}</el-button>
      </div>
      <el-input-number v-model="amount" :min="0" :step="10" :precision="2" style="width:100%" />
      <template #footer>
        <el-button @click="rechargeVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitRecharge">确认充值</el-button>
      </template>
    </el-dialog>

    <!-- 发券 -->
    <el-dialog v-model="couponVisible" title="发放优惠券" width="400px">
      <el-form label-width="86px">
        <el-form-item label="券名称">
          <el-input v-model="couponForm.title" placeholder="如 满100减20" />
        </el-form-item>
        <el-form-item label="抵扣金额">
          <el-input-number v-model="couponForm.amount" :min="0" :step="5" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="使用门槛">
          <el-input-number v-model="couponForm.min_spend" :min="0" :step="10" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="有效天数">
          <el-input-number v-model="couponForm.expire_days" :min="1" :step="1" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="couponVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCoupon">发放</el-button>
      </template>
    </el-dialog>

    <!-- 券明细 -->
    <el-dialog v-model="listVisible" :title="`优惠券明细 · ${current?.phone || ''}`" width="460px">
      <div v-if="!couponList.length" style="color:#9ca3af;font-size:13px;padding:10px 0">暂无优惠券</div>
      <div v-for="c in couponList" :key="c.id" class="coupon-line">
        <div>
          <b>{{ c.title }}</b>
          <div style="font-size:12px;color:#6b7280">
            满 ¥{{ Number(c.min_spend).toFixed(2) }} 可用 ·
            {{ c.expire_text }}
          </div>
        </div>
        <div style="text-align:right">
          <div style="color:#f97316;font-weight:700">-¥{{ Number(c.amount).toFixed(2) }}</div>
          <span class="status-badge" :class="c.status === 0 ? 's-3' : 's-4'">{{ c.status_text }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminSummary from '../components/AdminSummary.vue'
import AppIcon from '../components/AppIcon.vue'

const loadError = ref('')

const members = ref([])
const loading = ref(true)
const keyword = ref('')

const createVisible = ref(false)
const rechargeVisible = ref(false)
const couponVisible = ref(false)
const listVisible = ref(false)
const current = ref(null)
const submitting = ref(false)
const amount = ref(0)
const couponList = ref([])
const quickAmounts = [50, 100, 200]

const form = ref({ phone: '', name: '' })
const couponForm = ref({ title: '', amount: 20, min_spend: 100, expire_days: 30 })

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await adminAPI.members(keyword.value.trim())
    members.value = res.members || []
  } catch (e) {
    loadError.value = e.message + (members.value.length ? '（保留上次成功数据）' : '')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { phone: '', name: '' }
  createVisible.value = true
}

async function submitCreate() {
  const phone = form.value.phone.trim()
  if (!/^1\d{10}$/.test(phone)) {
    ElMessage.warning('请输入正确的 11 位手机号')
    return
  }
  submitting.value = true
  try {
    await adminAPI.createMember({ phone, name: form.value.name.trim() || null })
    ElMessage.success('会员已注册')
    createVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

function openRecharge(m) {
  current.value = m
  amount.value = 100
  rechargeVisible.value = true
}

async function submitRecharge() {
  if (!amount.value) return
  submitting.value = true
  try {
    await adminAPI.rechargeMember(current.value.id, amount.value)
    ElMessage.success(`已充值 ¥${amount.value}`)
    rechargeVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

function openCoupon(m) {
  current.value = m
  couponForm.value = { title: '', amount: 20, min_spend: 100, expire_days: 30 }
  couponVisible.value = true
}

async function submitCoupon() {
  if (!couponForm.value.title.trim()) {
    ElMessage.warning('请填写券名称')
    return
  }
  submitting.value = true
  try {
    await adminAPI.issueCoupon(current.value.id, { ...couponForm.value })
    ElMessage.success('优惠券已发放')
    couponVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function viewCoupons(m) {
  current.value = m
  try {
    const res = await adminAPI.memberDetail(m.id)
    couponList.value = res.coupons || []
    listVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>
