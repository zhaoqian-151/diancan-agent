<template>
  <div class="page">
    <AdminPageHeader title="原料库存" description="关注库存预警，及时补货，减少临时估清。"><button class="btn-ghost" :disabled="loading" @click="load"><AppIcon name="refresh" :size="15" />刷新库存</button><router-link class="btn-primary" to="/admin/menu">管理菜品</router-link></AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />
    <AdminSummary :loading="loading || (!!loadError && !ingredients.length)" :items="[
      {label:'原料种类', value:ingredients.length, note:'库存独立计量'},
      {label:'需补货', value:lowCount, note:'当前库存 ≤ 预警阈值', warning:true},
      {label:'库存充足', value:ingredients.filter(i => !i.low).length, note:'高于补货阈值'},
      {label:'已关联菜品', value:ingredients.filter(i => i.dishes?.length).length, note:'已建立菜品原料关联'}
    ]" />
    <div class="admin-toolbar"><AppIcon name="search" :size="17" /><input v-model="keyword" class="simple-search" placeholder="搜索原料或关联菜品" aria-label="搜索原料" /><select v-model="stockFilter" class="admin-filter-select" aria-label="库存状态"><option value="all">全部库存</option><option value="low">仅看需补货</option><option value="enough">仅看库存充足</option></select><span class="admin-result-count">{{ filteredIngredients.length }} 种原料</span></div>
    <div v-if="loading" class="empty-state">正在读取库存…</div>
    <template v-else>
      <div v-if="lowStock.length" class="low-banner"><b>补货提醒 · {{ lowStock.map(i => i.name).join('、') }}</b><br />不足单份用量时，相关菜品会自动下架。补货后请到菜品管理确认重新上架。</div>
      <div v-if="!loadError && !filteredIngredients.length" class="empty-state">{{ ingredients.length ? '没有符合条件的原料' : '还没有原料库存' }}</div>
      <div v-else class="inv-list"><div v-for="i in filteredIngredients" :key="i.id" class="inv-row" :class="{ low:i.low }">
        <div class="inv-main"><div class="inv-name">{{ i.name }}<span class="inv-unit">单位：{{ i.unit }}</span></div><div class="inv-dishes">关联菜品：{{ i.dishes?.length ? i.dishes.join('、') : '尚未关联' }}</div></div>
        <div class="inv-stock"><span class="inv-stock-num" :class="{low:i.low}">{{ i.stock }}</span> <span class="inv-stock-unit">{{ i.unit }}</span><div class="inv-threshold">预警 ≤ {{ i.threshold }} {{ i.unit }}</div></div>
        <span class="status-badge" :class="i.low ? 's-0' : 's-3'">{{ i.low ? '需补货' : '充足' }}</span>
        <div class="inv-actions"><button class="btn-sm btn-primary" @click="openRestock(i)">补货</button><button class="btn-sm btn-ghost" @click="openAdjust(i)">调整</button></div>
      </div></div>
    </template>

    <!-- 补货 -->
    <el-dialog v-model="restockVisible" title="原料补货" width="400px">
      <p style="margin:0 0 12px;color:#4b5563;font-size:14px">
        为 <b>{{ current?.name }}</b> 补货（当前库存 {{ current?.stock }} {{ current?.unit }}）：
      </p>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <el-button v-for="q in quickAdds" :key="q" @click="addAmount = q">
          +{{ q }}
        </el-button>
      </div>
      <el-input-number
        v-model="addAmount"
        :min="0"
        :step="1"
        :precision="1"
        style="width:100%"
      />
      <template #footer>
        <el-button @click="restockVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!addAmount"
          :loading="submitting"
          @click="submitRestock"
        >确认补货</el-button>
      </template>
    </el-dialog>

    <!-- 调整库存 / 阈值 -->
    <el-dialog v-model="adjustVisible" title="调整库存与阈值" width="400px">
      <div class="adjust-form">
        <label>直接设定库存（{{ current?.unit }}）</label>
        <el-input-number v-model="stockValue" :min="0" :step="1" :precision="1" style="width:100%" />
        <label style="margin-top:14px">补货预警阈值</label>
        <el-input-number v-model="thresholdValue" :min="0" :step="1" :precision="1" style="width:100%" />
      </div>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAdjust">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminSummary from '../components/AdminSummary.vue'
import AppIcon from '../components/AppIcon.vue'

const loadError = ref('')

const ingredients = ref([])
const lowStock = ref([])
const loading = ref(true)

const restockVisible = ref(false)
const adjustVisible = ref(false)
const current = ref(null)
const addAmount = ref(0)
const stockValue = ref(0)
const thresholdValue = ref(0)
const submitting = ref(false)

const quickAdds = [5, 10, 20]

const lowCount = computed(() => lowStock.value.length)
const keyword = ref(''), stockFilter = ref('all')
const filteredIngredients = computed(() => ingredients.value.filter(i => (!keyword.value.trim() || `${i.name} ${(i.dishes || []).join(' ')}`.includes(keyword.value.trim())) && (stockFilter.value === 'all' || Boolean(i.low) === (stockFilter.value === 'low'))))

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await adminAPI.inventory()
    ingredients.value = res.ingredients || []
    lowStock.value = res.low_stock || []
  } catch (e) {
    loadError.value = e.message + (ingredients.value.length ? '（保留上次成功数据）' : '')
  } finally {
    loading.value = false
  }
}

function openRestock(i) {
  current.value = i
  addAmount.value = 0
  restockVisible.value = true
}

async function submitRestock() {
  if (!addAmount.value) return
  submitting.value = true
  try {
    await adminAPI.updateIngredient(current.value.id, { add: addAmount.value })
    ElMessage.success(`已为 ${current.value.name} 补货 +${addAmount.value}`)
    restockVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

function openAdjust(i) {
  current.value = i
  stockValue.value = i.stock
  thresholdValue.value = i.threshold
  adjustVisible.value = true
}

async function submitAdjust() {
  submitting.value = true
  try {
    await adminAPI.updateIngredient(current.value.id, {
      stock: stockValue.value,
      threshold: thresholdValue.value,
    })
    ElMessage.success(`已更新：${current.value.name}`)
    adjustVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>
