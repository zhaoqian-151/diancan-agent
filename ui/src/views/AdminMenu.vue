<template>
  <div class="page admin-menu-page">
    <AdminPageHeader title="菜品管理" description="让菜单更好看，也让每道菜的信息清楚、准确。">
      <button class="btn-ghost" :disabled="loading" @click="load"><AppIcon name="refresh" :size="15" />刷新</button><button class="btn-primary" @click="openAddDialog">＋ 添加菜品</button>
    </AdminPageHeader>
    <LoadError :message="loadError" @retry="load" />
    <AdminSummary :loading="loading || !!loadError" :items="[
      {label:'全部菜品', value:menuItems.length, note:'当前门店菜单'},
      {label:'在售菜品', value:menuItems.filter(d => d.is_available).length, note:'顾客可加入购物车'},
      {label:'已下架', value:menuItems.filter(d => !d.is_available).length, note:'暂不接受点单', warning:true},
      {label:'菜品分类', value:categories.length, note:'按当前菜单统计'}
    ]" />
    <div class="admin-toolbar"><AppIcon name="search" :size="17" /><input v-model="keyword" class="simple-search" placeholder="搜索菜品名称或食材" aria-label="搜索菜品" /><select v-model="categoryFilter" class="admin-filter-select" aria-label="菜品分类"><option value="">全部分类</option><option v-for="c in categories" :key="c">{{ c }}</option></select><select v-model="availabilityFilter" class="admin-filter-select" aria-label="菜品销售状态"><option value="all">全部状态</option><option value="on">在售</option><option value="off">已下架</option></select><span class="admin-result-count">{{ filteredMenu.length }} 道菜品</span></div>
    <div class="card admin-menu-desktop" v-if="!loading && !loadError">
      <div class="table-scroll"><table class="admin-table"><thead><tr><th>菜品图片</th><th>菜品信息</th><th>分类</th><th>辣度</th><th>售价</th><th>销售状态</th><th>操作</th></tr></thead><tbody>
        <tr v-for="d in filteredMenu" :key="d.id"><td><DishImage class="admin-dish-thumb" :src="d.image_url" :name="d.dish_name" :vegetarian="d.is_vegetarian" /></td><td><div class="admin-dish-name">{{ d.dish_name }}</div><div class="admin-dish-desc">{{ truncate(d.description, 42) }}</div></td><td><span class="subtle-tag">{{ d.category }}</span></td><td>{{ d.spice_text }}</td><td><span class="admin-price">{{ d.formatted_price }}</span></td><td><label class="avail-switch"><input type="checkbox" :aria-label="`${d.dish_name}上下架`" :checked="d.is_available" :disabled="savingId === d.id" @change="toggleAvail(d)" /><span>{{ d.is_available ? '在售' : '已下架' }}</span></label></td><td><button class="btn-ghost btn-sm" @click="editDish(d)">编辑</button></td></tr>
        <tr v-if="!filteredMenu.length"><td colspan="7" class="empty-state">{{ menuItems.length ? '没有符合筛选条件的菜品' : '暂无菜品，点击添加菜品建立菜单' }}</td></tr>
      </tbody></table></div>
    </div>
    <div v-else-if="loading" class="empty-state">正在读取菜品…</div>
    <div v-if="!loading && !loadError" class="admin-menu-mobile"><article v-for="d in filteredMenu" :key="d.id" class="admin-mobile-dish"><DishImage class="admin-mobile-dish-photo" :src="d.image_url" :name="d.dish_name" :vegetarian="d.is_vegetarian" /><div class="admin-mobile-dish-info"><strong>{{ d.dish_name }}</strong><small>{{ d.category }} · {{ d.spice_text }}</small><span class="admin-price">{{ d.formatted_price }}</span></div><div class="admin-mobile-dish-actions"><button class="btn-ghost btn-sm" @click="editDish(d)">编辑</button><label class="avail-switch"><input type="checkbox" :aria-label="`${d.dish_name}上下架`" :checked="d.is_available" :disabled="savingId === d.id" @change="toggleAvail(d)" /><span>{{ d.is_available ? '在售' : '下架' }}</span></label></div></article><div v-if="!filteredMenu.length" class="empty-state">没有符合条件的菜品</div></div>
    <p class="admin-inline-note">新增菜品支持自动生成配图；AI 图片会在顾客端标注，可随时替换为实拍。</p>

    <!-- 添加菜品对话框 -->
    <el-dialog v-model="addVisible" :title="editingId ? '编辑菜品' : '添加菜品'" width="600px" :close-on-click-modal="false" :close-on-press-escape="!generating && !submitting" :show-close="!generating && !submitting">
      <el-form label-width="90px" ref="addFormRef" :model="addForm" :rules="addRules" :disabled="generating || submitting">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="菜品名" prop="dish_name">
              <el-input v-model="addForm.dish_name" placeholder="如：宫保鸡丁" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="价格" prop="price">
              <el-input-number
                v-model="addForm.price"
                :min="0.1"
                :step="0.1"
                :precision="1"
                style="width:100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="分类" prop="category">
              <el-select v-model="addForm.category" filterable allow-create default-first-option style="width:100%">
                <el-option label="川菜" value="川菜" />
                <el-option label="素食" value="素食" />
                <el-option label="鲁菜" value="鲁菜" />
                <el-option label="粤菜" value="粤菜" />
                <el-option label="江浙菜" value="江浙菜" />
                <el-option label="饮品" value="饮品" />
                <el-option label="主食" value="主食" />
                <el-option label="凉菜" value="凉菜" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="辣度">
              <el-select v-model="addForm.spice_level" style="width:100%">
                <el-option label="不辣" :value="0" />
                <el-option label="微辣" :value="1" />
                <el-option label="中辣" :value="2" />
                <el-option label="重辣" :value="3" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="描述">
          <el-input v-model="addForm.description" type="textarea" :rows="2" placeholder="菜品简介" />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="口味特点">
              <el-input v-model="addForm.flavor" placeholder="如：麻辣鲜香" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="烹饪方法">
              <el-input v-model="addForm.cooking_method" placeholder="如：爆炒" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="主要食材">
              <el-input v-model="addForm.main_ingredients" placeholder="逗号分隔，如：鸡胸肉,花生" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="过敏原">
              <el-input v-model="addForm.allergens" placeholder="如：花生,鱼类" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="素食">
          <el-switch v-model="addForm.is_vegetarian" />
        </el-form-item>

        <el-form-item label="图片">
          <div class="dish-image-editor">
              <DishImage class="image-editor-preview" :src="addForm.image_url" :name="addForm.dish_name" :vegetarian="addForm.is_vegetarian" />
            <div style="flex:1">
              <el-input v-model="addForm.image_url" size="small" placeholder="自动生成，或填写菜品实拍地址" />
              <el-button class="generate-image-button" :loading="generating" :disabled="!addForm.dish_name.trim()" @click="generateImage">{{ addForm.image_url ? '重新生成配图' : 'AI 生成菜品图片' }}</el-button>
              <el-checkbox v-model="autoImage">保存时自动生成缺失图片</el-checkbox>
              <p class="muted">生成图片按菜名和食材绘制，前台标注 AI 示意，可替换为实拍。</p>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <div v-if="generating" class="image-job-progress" role="status"><span class="image-job-spinner"></span><div><strong>{{ generationMessage }}</strong><p>一般需要约 20–90 秒，请保持页面打开。</p></div></div>
      <el-alert v-if="generationError" :title="generationError" type="error" :closable="false" show-icon style="margin:12px 0" />
      <template #footer>
        <el-button :disabled="generating || submitting" @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting || generating" @click="submitAdd">
          {{ generating ? '正在生成配图' : '保存菜品' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { menuAPI, adminAPI } from '../api'
import LoadError from '../components/LoadError.vue'
import DishImage from '../components/DishImage.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminSummary from '../components/AdminSummary.vue'
import AppIcon from '../components/AppIcon.vue'


const menuItems = ref([])
const keyword = ref(''), categoryFilter = ref(''), availabilityFilter = ref('all')
const categories = computed(() => [...new Set(menuItems.value.map(d => d.category))].filter(Boolean))
const filteredMenu = computed(() => menuItems.value.filter(d => (!keyword.value.trim() || `${d.dish_name} ${d.main_ingredients || ''}`.includes(keyword.value.trim())) && (!categoryFilter.value || d.category === categoryFilter.value) && (availabilityFilter.value === 'all' || Boolean(d.is_available) === (availabilityFilter.value === 'on'))))
const loading = ref(true)
const savingId = ref(null)

const addVisible = ref(false)
const submitting = ref(false)
const editingId = ref(null), loadError = ref('')
const addFormRef = ref(null)
const autoImage = ref(true), generating = ref(false), generationMessage = ref(''), generationError = ref('')
let disposed = false
onUnmounted(() => { disposed = true })

const defaultForm = () => ({
  dish_name: '',
  price: 18.00,
  category: '川菜',
  description: '',
  spice_level: 0,
  flavor: '',
  main_ingredients: '',
  cooking_method: '',
  is_vegetarian: false,
  allergens: '',
  image_url: '',
  is_available: true,
})
const addForm = reactive(defaultForm())

const addRules = {
  dish_name: [{ required: true, message: '请输入菜品名', trigger: 'blur' }],
  price: [{ required: true, message: '请输入价格', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { menu_items } = await menuAPI.getList()
    menuItems.value = menu_items || []
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

async function toggleAvail(dish) {
  savingId.value = dish.id
  try {
    const updated = await adminAPI.updateMenuItem(dish.id, {
      is_available: !dish.is_available,
    })
    dish.is_available = updated.is_available
    ElMessage.success(`${dish.dish_name} 已${updated.is_available ? '上架' : '下架'}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    savingId.value = null
  }
}

function openAddDialog() {
  if (generating.value || submitting.value) return
  editingId.value = null
  generationError.value = ''; generationMessage.value = ''; autoImage.value = true
  Object.assign(addForm, defaultForm())
  addVisible.value = true
}

function editDish(dish) {
  if (generating.value || submitting.value) return
  editingId.value = dish.id
  generationError.value = ''; generationMessage.value = ''; autoImage.value = true
  Object.assign(addForm, defaultForm(), dish, { image_url: dish.image_url?.includes('text_to_image') ? '' : dish.image_url || '' })
  addVisible.value = true
}

async function submitAdd() {
  if (!addFormRef.value || submitting.value || generating.value) return
  try { await addFormRef.value.validate() } catch { return }
  submitting.value = true
  try {
    if (autoImage.value && !addForm.image_url && !(await generateImage())) return
    if (disposed) return
    const payload = { ...addForm }
    const created = editingId.value ? await adminAPI.updateMenuItem(editingId.value, payload) : await adminAPI.createMenuItem(payload)
    ElMessage.success(`已保存：${created.dish_name}`)
    addVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function generateImage() {
  if (generating.value || !addForm.dish_name.trim()) return false
  generating.value = true; generationError.value = ''; generationMessage.value = '正在提交图片生成任务…'
  try {
    const { dish_name, category, description, main_ingredients, cooking_method, is_vegetarian } = addForm
    let job = await adminAPI.generateDishImage({ dish_name, category, description, main_ingredients, cooking_method, is_vegetarian })
    const deadline = Date.now() + 240000
    while (!disposed && Date.now() < deadline) {
      generationMessage.value = job.message || '正在生成菜品图片…'
      if (job.status === 'succeeded' && job.image_url) {
        addForm.image_url = job.image_url
        ElMessage.success('菜品图片已生成并保存')
        return true
      }
      if (job.status === 'failed') throw new Error(job.message || '图片生成失败，请重试')
      await new Promise(resolve => setTimeout(resolve, 2000))
      if (disposed) return false
      job = await adminAPI.dishImageJob(job.job_id)
    }
    if (!disposed) throw new Error('图片生成等待超时，请稍后重试')
  } catch (e) {
    generationError.value = e.message
  } finally {
    generating.value = false
  }
  return false
}

function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

onMounted(load)
</script>
