<template>
  <div class="page">
    <AdminPageHeader title="桌台管理" description="一眼查看空闲与用餐状态，安排每一位到店客人。"><button class="btn-ghost" :disabled="loading" @click="load"><AppIcon name="refresh" :size="15" />刷新桌台</button></AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />
    <AdminSummary :loading="loading || (!!loadError && !tables.length)" :items="[
      {label:'全部桌台', value:tables.length, note:`共 ${tables.reduce((n,t) => n + Number(t.seats),0)} 个座位`},
      {label:'空闲可用', value:freeCount, note:'可直接开台接待'},
      {label:'正在用餐', value:tables.filter(t => t.status === 1).length, note:'支持换台与并台', warning:true},
      {label:'已预订', value:tables.filter(t => t.status === 2).length, note:'当前预订状态桌台'}
    ]" />
    <div class="admin-tab" aria-label="桌台状态筛选"><button v-for="f in tableFilters" :key="f.label" :class="{active:tableFilter === f.value}" :aria-pressed="tableFilter === f.value" @click="tableFilter = f.value">{{ f.label }}<span class="tab-count">{{ tables.filter(t => f.value === null || t.status === f.value).length }}</span></button></div>
    <div v-if="loading" class="empty-state">正在读取桌台…</div>
    <div v-else-if="!loadError && !filteredTables.length" class="empty-state"><AppIcon name="table" :size="32" /><strong>当前没有{{ tableFilter === null ? '' : tableFilters.find(f => f.value === tableFilter)?.label }}桌台</strong><span>切换筛选查看其他桌台</span></div>
    <div v-else class="table-grid">
      <article v-for="t in filteredTables" :key="t.id" class="table-card" :class="`t-${t.status}`"><div class="table-card-head"><span class="table-no">{{ t.table_no }}</span><span class="status-badge" :class="t.status === 1 ? 's-1' : t.status === 2 ? 's-2' : 's-3'">{{ t.status_text }}</span></div><div class="admin-table-visual"><AppIcon name="table" :size="40" /><div class="table-seats">{{ t.seats }} 人桌</div></div><div class="table-actions"><button v-if="t.status === 0" class="btn-sm btn-primary" @click="openTable(t)">开台接待</button><template v-else-if="t.status === 1"><button class="btn-sm btn-ghost" @click="openDialog(t, 'change')">换台</button><button class="btn-sm btn-ghost" @click="openDialog(t, 'merge')">并台</button><button class="btn-sm btn-primary" @click="closeTable(t)">结账</button></template><span v-else class="muted">已预订 · 暂不开放开台</span></div></article>
    </div>

    <!-- 换台 / 并台 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'change' ? '换台' : '并台'"
      width="380px"
    >
      <p style="margin:0 0 12px;color:#4b5563;font-size:14px">
        把 <b>{{ currentTable?.table_no }}</b> 桌
        {{ dialogMode === 'change' ? '换到' : '并入' }}：
      </p>
      <el-select v-model="targetTableNo" placeholder="请选择目标桌台" style="width:100%">
        <el-option
          v-for="t in targetOptions"
          :key="t.id"
          :label="`${t.table_no}（${t.seats} 座 · ${t.status_text}）`"
          :value="t.table_no"
        />
      </el-select>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!targetTableNo"
          :loading="submitting"
          @click="submitDialog"
        >确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminSummary from '../components/AdminSummary.vue'
import AppIcon from '../components/AppIcon.vue'

const loadError = ref('')

const tables = ref([])
const loading = ref(true)

const dialogVisible = ref(false)
const dialogMode = ref('change')
const currentTable = ref(null)
const targetTableNo = ref('')
const submitting = ref(false)

const freeCount = computed(() => tables.value.filter(t => t.status === 0).length)
const tableFilter = ref(null)
const tableFilters = [{label:'全部', value:null},{label:'空闲', value:0},{label:'用餐中', value:1},{label:'已预订', value:2}]
const filteredTables = computed(() => tables.value.filter(t => tableFilter.value === null || t.status === tableFilter.value))

const targetOptions = computed(() =>
  tables.value.filter(
    t => t.table_no !== currentTable.value?.table_no && t.status === (dialogMode.value === 'change' ? 0 : 1),
  ),
)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await adminAPI.tables()
    tables.value = res.tables || []
  } catch (e) {
    loadError.value = e.message + (tables.value.length ? '（保留上次成功数据）' : '')
  } finally {
    loading.value = false
  }
}

async function openTable(t) {
  try {
    await adminAPI.openTable(t.table_no)
    ElMessage.success(`已开台：${t.table_no}`)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openDialog(t, mode) {
  currentTable.value = t
  dialogMode.value = mode
  targetTableNo.value = ''
  dialogVisible.value = true
}

async function submitDialog() {
  if (!targetTableNo.value) return
  submitting.value = true
  try {
    const from = currentTable.value.table_no
    const to = targetTableNo.value
    if (dialogMode.value === 'change') {
      await adminAPI.changeTable(from, to)
      ElMessage.success(`已换台：${from} → ${to}`)
    } else {
      await adminAPI.mergeTable(from, to)
      ElMessage.success(`已并台：${from} 并入 ${to}`)
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function closeTable(t) {
  try {
    await ElMessageBox.confirm(
      `确认对 ${t.table_no} 桌结账清台？（该桌未完成订单将置为已完成）`,
      '结账确认',
      { type: 'warning', confirmButtonText: '结账', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const res = await adminAPI.closeTable(t.table_no, true)
    ElMessage.success(`已结账：${t.table_no}，完成 ${res.settled_orders} 单`)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>
