<template>
  <div class="page dining-home">
    <div class="page-heading dining-heading"><div><h1>今天吃点好的</h1><p>{{ shopName }}</p></div><router-link to="/orders" class="btn-ghost"><AppIcon name="orders" :size="16" />我的订单</router-link></div>
    <div class="first-screen-grid">
      <section class="food-hero" aria-label="餐厅美食介绍">
        <img class="food-hero-photo" src="/images/generated/hero-feast.webp" alt="宫保鸡丁、米饭与蒜蓉西兰花的美食示意" fetchpriority="high" />
        <div class="food-hero-shade"></div>
        <div class="food-hero-copy"><span class="hero-invitation">一餐一味，认真对待</span><h2>好好吃饭，<br />好好生活。</h2><p>想吃的这一口，<br />就在今天的菜单里。</p><a href="#menu" class="hero-menu-link">挑选你的好味道 <AppIcon name="arrow" :size="17" /></a></div>
        <div class="food-hero-caption"><span><AppIcon name="clock" :size="14" />{{ shopInfo?.business_hours || '营业时间请咨询门店' }}</span><span v-if="shopInfo?.delivery_radius_km">配送 {{ shopInfo.delivery_radius_km }} 公里内</span></div><span class="hero-image-label">AI 美食示意图</span>
      </section>
      <aside class="panel" id="ordering-assistant" style="scroll-margin-top:20px">
        <!-- AI 助手 -->
        <div class="panel-header">
          <span class="assistant-icon"><AppIcon name="spark" :size="19" /></span><div>点餐小助手<small>告诉我你的口味，今天这顿我来帮你选</small></div><span class="ai-label">AI</span>
        </div>
        <div class="panel-body">
          <div class="chat-messages" ref="chatBox" role="log" aria-live="polite" aria-label="点餐助手对话">
            <div v-if="!chatHistory.length" class="assistant-welcome"><span class="welcome-spark"><AppIcon name="spark" :size="30" /></span><h3>不纠结，吃点对胃口的</h3><p>告诉我你的口味、预算或忌口，<br />我会根据当前菜单为你推荐。</p><div class="chat-suggestions"><button v-for="q in suggestions" :key="q" @click="ask(q)">{{ q }}<AppIcon name="arrow" :size="13" /></button></div></div>
            <div
              v-for="(msg, i) in chatHistory"
              :key="i"
              class="chat-bubble"
              :class="msg.role"
              v-html="formatMarkdown(msg.content)"
            ></div>
            <div v-if="chatLoading" class="chat-bubble assistant">
              <em>思考中…</em>
            </div>
          </div>
          <div class="chat-input-row">
            <textarea
              v-model="chatInput"
              :rows="2"
              placeholder="我想吃点辣的 / 推荐个素菜"
              aria-label="向点餐助手提问"
              @keydown.enter.exact="handleChatEnter"
            ></textarea>
            <button :disabled="chatLoading || !chatInput.trim()" @click="sendChat">
              {{ chatLoading ? '…' : '发送' }}
            </button>
          </div>
          <p class="ai-footnote">推荐仅供选餐参考，过敏与忌口请向门店确认。</p>
        </div>

        <LoadError v-if="cartError" :message="cartError" @retry="loadCart" />
        <div class="assistant-cart-summary" :class="{ 'has-cart': cartCount > 0 }">
          <div><AppIcon name="cart" :size="18" /><span>{{ cartCount ? `已选 ${cartCount} 件` : '好味道，从选一道菜开始' }}</span><b v-if="cartCount">¥{{ cartTotal.toFixed(2) }}</b></div>
          <button class="btn-primary btn-sm" :disabled="!cartCount || cartBusy" @click="showCart = true">查看购物车</button>
        </div>
      </aside>
    </div>
    <div class="menu-toolbar" id="menu" style="scroll-margin-top:20px"><div class="section-label"><h2>本店菜单</h2><span v-if="!loading && !menuError">{{ menuItems.length }} 道菜品 · 按需选择</span></div><label class="menu-search"><AppIcon name="search" :size="17" /><input v-model="search" placeholder="搜索菜名、食材或口味" aria-label="搜索菜品" /><button v-if="search" @click="search = ''" aria-label="清除搜索">×</button></label></div>
    <!-- 分类栏 -->
    <div class="cat-bar">
      <button
        v-for="cat in allCategories"
        :key="cat"
        class="cat-chip"
        :class="{ active: activeCat === cat }"
        @click="activeCat = cat"
        :aria-pressed="activeCat === cat"
      >{{ cat }}<span class="category-count">{{ cat === '全部' ? menuItems.length : menuItems.filter(d => d.category === cat).length }}</span></button>
    </div>
    <div class="diet-filters"><label><input type="checkbox" v-model="vegetarianOnly" />只看素食</label><label><input type="checkbox" v-model="mildOnly" />只看不辣</label><button v-if="search || vegetarianOnly || mildOnly || activeCat !== '全部'" class="filter-reset" @click="resetFilters">重置筛选</button><span>{{ filteredDishes.length }} 道符合条件</span></div>

    <!-- 主布局：菜品 + 右侧面板 -->
    <div class="split-layout">
      <!-- 菜品列表 -->
      <section>
        <LoadError v-if="menuError" :message="menuError" @retry="loadMenu" />
        <div v-if="loading" class="empty-state">
          <div class="emoji">⏳</div>
          <div>菜单加载中...</div>
        </div>
        <div v-else-if="!menuError && filteredDishes.length === 0" class="empty-state">
          <div class="emoji">🍽️</div>
          <div>没有找到符合条件的菜品</div><button class="btn-ghost btn-sm" @click="resetFilters">查看全部菜品</button>
        </div>
        <div v-else class="menu-grid">
          <div
            v-for="dish in filteredDishes"
            :key="dish.id"
            class="dish-card"
            :class="{
              highlighted: highlightedIds.includes(dish.id),
              unavailable: !dish.is_available,
            }"
          >
            <div class="dish-img">
              <span v-if="!dish.is_available" class="dish-badge-off">已售罄</span>
              <DishImage :src="dish.image_url" :name="dish.dish_name" :category="dish.category" :vegetarian="dish.is_vegetarian" />
            </div>
            <div class="dish-info">
              <div class="dish-name-row">
                <h3 class="dish-name">{{ dish.dish_name }}</h3>
                <span class="dish-price">{{ dish.formatted_price }}</span>
              </div>
              <p class="dish-desc">{{ dish.description }}</p>
              <p class="allergen-note" v-if="dish.allergens">过敏原：{{ dish.allergens }}</p>
              <details v-if="dish.main_ingredients || dish.cooking_method" class="dish-details"><summary>食材与做法</summary><p>食材：{{ dish.main_ingredients || '尚未填写' }}<br />做法：{{ dish.cooking_method || '尚未填写' }}</p></details>
              <div class="dish-tags">
                <span class="dish-tag">{{ dish.category }}</span>
                <span
                  class="dish-tag"
                  :class="`level-${dish.spice_level}`"
                >{{ dish.spice_text }}</span>
                <span v-if="dish.is_vegetarian" class="dish-tag veggie">素食</span>
                <span v-if="highlightedIds.includes(dish.id)" class="dish-tag rec">推荐</span>
              </div>
              <div class="dish-actions">
                <button
                  class="btn-add-cart"
                  :disabled="!dish.is_available || cartBusy"
                  @click.stop="addToCart(dish)"
                  style="position:relative"
                >
                  {{ dish.is_available ? '+ 加入' : '暂不可点' }}
                  <span
                    v-if="cartQtyMap[dish.id]"
                    class="cart-btn-badge"
                  >{{ cartQtyMap[dish.id] }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右侧面板 -->

    </div>

    <!-- 浮动购物车按钮 -->
    <button v-if="cartCount > 0" class="fab-cart" aria-label="打开购物车" @click="showCart = true">
      🛒
      <span class="badge">{{ cartCount }}</span>
    </button>

    <!-- 购物车抽屉 -->
    <el-drawer
      v-model="showCart"
      title="购物车"
      direction="rtl"
      size="380px"
      class="cart-drawer"
    >
      <div v-if="cartList.length === 0" class="empty-state">
        <div class="emoji">🛒</div>
        <div>购物车是空的</div>
      </div>
      <template v-else>
        <div class="cart-list">
          <div v-for="item in cartList" :key="item.dish_id" class="cart-item">
            <img
              class="cart-item-img"
              :src="dishImage(item.dish_id)"
              :alt="item.dish_name"
              v-if="dishImage(item.dish_id)"
            />
            <div class="cart-item-info">
              <div class="cart-item-name">{{ item.dish_name }}</div>
              <div class="cart-item-price">{{ item.formatted_price }} × {{ item.quantity }}</div>
              <div class="qty-ctrl">
                <button :disabled="cartBusy" :aria-label="`减少${item.dish_name}`" @click="changeQty(item.dish_id, -1)">−</button>
                <span>{{ item.quantity }}</span>
                <button :disabled="cartBusy" :aria-label="`增加${item.dish_name}`" @click="changeQty(item.dish_id, 1)">+</button>
              </div>
            </div>
          </div>
        </div>
        <div class="cart-footer">
          <div class="cart-total">
            <span class="cart-total-label">合计</span>
            <span class="cart-total-amount">¥{{ cartTotal.toFixed(2) }}</span>
          </div>
          <button
            class="btn-primary"
            style="width: 100%; height: 44px; font-size: 15px;"
            @click="goCheckout"
          >去结算</button>
        </div>
      </template>
    </el-drawer>

    <!-- 结算弹窗 -->
    <el-dialog
      v-model="checkoutVisible"
      title="确认下单"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="orderFormRef"
        :model="orderForm"
        :rules="orderRules"
        label-width="82px"
      >
        <el-form-item label="配送方式" prop="delivery_mode">
          <el-radio-group v-model="orderForm.delivery_mode">
            <el-radio :value="2">外卖配送</el-radio>
            <el-radio :value="1">到店自取</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 会员识别：余额支付 + 优惠券 -->
        <el-form-item label="会员">
          <div style="width:100%">
            <div style="display:flex;gap:8px">
              <el-input
                v-model="memberPhone"
                maxlength="11"
                placeholder="输入会员手机号查询优惠券"
                @keyup.enter="lookupMember"
              />
              <el-button :loading="memberLoading" @click="lookupMember">识别</el-button>
            </div>
            <div v-if="memberInfo" class="member-box">
              <div class="member-box-head">
                <b>{{ memberInfo.name || '会员' }}</b>
                <span class="member-level">{{ memberInfo.level_text }}</span>
                <span style="margin-left:auto;color:#059669;font-weight:700">余额 ¥{{ Number(memberInfo.balance).toFixed(2) }}</span>
              </div>
              <div style="font-size:12px;color:#6b7280;margin:4px 0">积分 {{ memberInfo.points }}</div>
              <el-select
                v-model="selectedCouponId"
                placeholder="选择优惠券（可不选）"
                clearable
                style="width:100%"
              >
                <el-option
                  v-for="c in memberInfo.usable_coupons"
                  :key="c.id"
                  :label="`${c.title}（满${c.min_spend}减${c.amount}）`"
                  :value="c.id"
                  :disabled="cartTotal < c.min_spend"
                />
              </el-select>
            </div>
          </div>
        </el-form-item>

        <el-alert title="在线支付尚未接入。提交后订单保留为待支付，请联系门店确认收款方式。" type="info" :closable="false" style="margin-bottom:18px" />

        <el-form-item label="联系人" prop="contact_name">
          <el-input v-model="orderForm.contact_name" placeholder="您的姓名" />
        </el-form-item>

        <el-form-item label="手机号" prop="contact_phone">
          <el-input
            v-model="orderForm.contact_phone"
            maxlength="11"
            placeholder="11 位手机号"
          />
        </el-form-item>

        <el-form-item
          v-if="orderForm.delivery_mode === 2"
          label="配送地址"
          prop="delivery_address"
        >
          <el-input
            v-model="orderForm.delivery_address"
            type="textarea"
            :rows="2"
            placeholder="请写详细地址，如：重庆市大渡口人民医院"
          />
          <div style="font-size:12px;color:#9ca3af;line-height:1.5">
            外卖配送需详细地址，提交时会自动核验是否在配送范围内
          </div>
        </el-form-item>

        <el-form-item v-else label="取餐门店">
          <div style="font-size:13px;color:#4b5563;line-height:1.6">
            {{ shopName }}<br />
            <span style="color:#9ca3af">到店报手机号取餐，无需填写配送地址</span>
          </div>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="rangeError"
        :title="rangeError"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 4px"
      />

      <div class="checkout-summary">
        <div class="checkout-row"><span>共 {{ cartCount }} 件</span><span>¥{{ cartTotal.toFixed(2) }}</span></div>
        <div v-if="discountAmount > 0" class="checkout-row discount">
          <span>优惠券抵扣</span><span>- ¥{{ discountAmount.toFixed(2) }}</span>
        </div>
        <div class="checkout-row total">
          <span>应付</span>
          <span>¥{{ payableAmount.toFixed(2) }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="checkoutVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitOrder">
          {{ orderForm.delivery_mode === 2 ? '核验地址并提交订单' : '提交订单' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import DishImage from '../components/DishImage.vue'
import LoadError from '../components/LoadError.vue'
import { ElMessage } from 'element-plus'
import { menuAPI, chatAPI, deliveryAPI, cartAPI, orderAPI, shopAPI, memberAPI } from '../api'

// ------------------ 菜单 ------------------
const menuItems = ref([])
const allCategories = ref(['全部'])
const activeCat = ref('全部')
const loading = ref(false)
const highlightedIds = ref([])
const menuError = ref(''), cartError = ref(''), search = ref(''), vegetarianOnly = ref(false), mildOnly = ref(false), cartBusy = ref(false), shopInfo = ref(null)
const router = useRouter()
const suggestions = ['推荐不辣的菜', '20 元以内有什么素菜？', '门店营业时间是？']
function resetFilters() { search.value = ''; vegetarianOnly.value = false; mildOnly.value = false; activeCat.value = '全部' }
function ask(q) { chatInput.value = q; sendChat() }
function handleChatEnter(event) { if (event.isComposing) return; event.preventDefault(); sendChat() }

const filteredDishes = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return menuItems.value.filter(d => (activeCat.value === '全部' || d.category === activeCat.value) && (!vegetarianOnly.value || d.is_vegetarian) && (!mildOnly.value || d.spice_level === 0) && (!keyword || [d.dish_name, d.main_ingredients, d.flavor, d.description].join(' ').toLowerCase().includes(keyword)))
})

async function loadMenu() {
  loading.value = true
  menuError.value = ''
  try {
    const { menu_items = [], categories = [] } = await menuAPI.getList()
    menuItems.value = menu_items
    allCategories.value = ['全部', ...categories]
  } catch (e) {
    menuError.value = e.message
  } finally {
    loading.value = false
  }
}

// ------------------ AI 聊天 ------------------
const chatHistory = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatBox = ref(null)
let sessionId = null

function formatMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/^- (.*)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n/g, '<br/>')
}

async function sendChat() {
  const q = chatInput.value.trim()
  if (!q || chatLoading.value) return
  chatHistory.value.push({ role: 'user', content: q })
  chatInput.value = ''
  chatLoading.value = true
  await nextTick()
  scrollChat()
  try {
    const res = await chatAPI.sendMessage(q, sessionId)
    sessionId = res.session_id
    chatHistory.value.push({ role: 'assistant', content: res.response || '' })
    // 推荐菜品高亮
    highlightedIds.value = res.menu_ids || []
    if (res.menu_ids?.length) {
      resetFilters()
      if (menuItems.value.length === 0) await loadMenu()
    }
  } catch (e) {
    chatHistory.value.push({ role: 'assistant', content: '抱歉，出错了：' + e.message })
  } finally {
    chatLoading.value = false
    scrollChat()
  }
}

function scrollChat() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

// ------------------ 购物车 ------------------
const showCart = ref(false)
const cartList = ref([])

const cartCount = computed(() =>
  cartList.value.reduce((s, i) => s + i.quantity, 0),
)
const cartTotal = computed(() =>
  cartList.value.reduce((s, i) => s + i.subtotal, 0),
)
const cartQtyMap = computed(() => {
  const map = {}
  for (const item of cartList.value) {
    map[item.dish_id] = item.quantity
  }
  return map
})

async function loadCart() {
  try {
    const res = await cartAPI.get()
    cartList.value = res.items || []
    cartError.value = ''
  } catch (e) { cartError.value = e.message }
}

async function addToCart(dish) {
  if (cartBusy.value) return
  cartBusy.value = true
  try {
    await cartAPI.add(dish.id, 1)
    ElMessage.success(`已加入：${dish.dish_name}`)
    await loadCart()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    cartBusy.value = false
  }
}

async function changeQty(dishId, delta) {
  if (cartBusy.value) return
  const item = cartList.value.find(i => i.dish_id === dishId)
  if (!item) return
  const nextQty = Math.max(0, item.quantity + delta)
  cartBusy.value = true
  try {
    await cartAPI.set(dishId, nextQty)
    await loadCart()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    cartBusy.value = false
  }
}

function dishImage(dishId) {
  const d = menuItems.value.find(m => m.id === dishId)
  return d?.image_url && !d.image_url.includes('text_to_image') ? d.image_url : ''
}

// ------------------ 结算 ------------------
const checkoutVisible = ref(false)
const submitting = ref(false)
const orderFormRef = ref(null)
const rangeError = ref('')
const shopName = ref('本店')

const emptyOrderForm = () => ({
  delivery_mode: 2,
  contact_name: '',
  contact_phone: '',
  delivery_address: '',
})
const orderForm = ref(emptyOrderForm())

// 会员识别 / 优惠券
const memberPhone = ref('')
const memberInfo = ref(null)
const selectedCouponId = ref(null)
const memberLoading = ref(false)

const selectedCoupon = computed(() =>
  (memberInfo.value?.usable_coupons || []).find(c => c.id === selectedCouponId.value) || null,
)
// 满足使用门槛才计抵扣
const discountAmount = computed(() => {
  const c = selectedCoupon.value
  if (!c || cartTotal.value < c.min_spend) return 0
  return Math.min(Number(c.amount), cartTotal.value)
})
const payableAmount = computed(() => Math.max(cartTotal.value - discountAmount.value, 0))

async function lookupMember() {
  const phone = memberPhone.value.trim()
  if (!/^1[3-9]\d{9}$/.test(phone)) {
    ElMessage.warning('请输入正确的 11 位手机号')
    return
  }
  memberLoading.value = true
  try {
    const res = await memberAPI.lookup(phone)
    if (!res.member) {
      memberInfo.value = null
      selectedCouponId.value = null
      ElMessage.info('该手机号还不是会员，可联系门店登记，也可不使用会员权益下单')
      return
    }
    memberInfo.value = res.member
    selectedCouponId.value = null
    ElMessage.success(`已识别会员：${res.member.name || res.member.phone}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    memberLoading.value = false
  }
}

// 地址只需写到「具体地点」即可，不强制门牌号（如：重庆市大渡口人民医院）
const ADDRESS_HINT_RE = /(省|市|区|县|镇|乡|村|路|街|道|巷|弄|胡同|大道|小区|花园|广场|大厦|公寓|中心|公园|医院|学校|大学|学院|车站|机场|地铁|酒店|宾馆|超市|商场|市场|馆|院|校|园|城|号|栋|幢|单元|室|楼)/

function validateDeliveryAddress(_rule, value, callback) {
  const s = (value || '').trim()
  if (!s) return callback(new Error('外卖配送需要填写收货地址'))
  if (s.length < 5 || !ADDRESS_HINT_RE.test(s)) {
    return callback(new Error('请写详细一些，具体到某条路、小区、医院、学校等即可'))
  }
  callback()
}

const orderRules = {
  contact_name: [{ required: true, message: '请填写联系人姓名', trigger: 'blur' }],
  contact_phone: [
    { required: true, message: '请填写手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入 11 位有效手机号', trigger: 'blur' },
  ],
  delivery_address: [
    { required: true, validator: validateDeliveryAddress, trigger: 'blur' },
  ],
}

function goCheckout() {
  if (cartList.value.length === 0) return
  rangeError.value = ''
  orderFormRef.value?.clearValidate()
  checkoutVisible.value = true
}

async function submitOrder() {
  if (submitting.value) return
  rangeError.value = ''
  try {
    await orderFormRef.value.validate()
  } catch {
    return // 表单项的内联错误已展示在本页
  }

  const { contact_name, contact_phone, delivery_address, delivery_mode } = orderForm.value
  const isDelivery = delivery_mode === 2
  submitting.value = true
  try {
    // 外卖配送：先核验配送范围，超出范围直接在本页提示
    if (isDelivery) {
      const chk = await deliveryAPI.checkRange(delivery_address.trim(), 2)
      if (chk.low_confidence) {
        rangeError.value = chk.message || '没能识别这个地址，请补充更具体的地点'
        return
      }
      if (!chk.success) {
        rangeError.value = chk.message || '地址解析失败，请检查后重试'
        return
      }
      if (!chk.in_range) {
        rangeError.value = chk.message || '该地址超出配送范围'
        return
      }
    }

    const useMemberId = memberInfo.value ? memberInfo.value.id : null
    const useCouponId = discountAmount.value > 0 ? selectedCouponId.value : null
    await orderAPI.create({
      delivery_mode,
      contact_name: contact_name.trim(),
      contact_phone: contact_phone.trim(),
      delivery_address: isDelivery ? delivery_address.trim() : null,
      member_id: useMemberId,
      coupon_id: useCouponId,
    })
    ElMessage.success('订单已提交，当前待支付。请联系门店确认收款方式。')
    checkoutVisible.value = false
    showCart.value = false
    orderForm.value = emptyOrderForm()
    memberPhone.value = ''
    memberInfo.value = null
    selectedCouponId.value = null
    await loadCart()
    router.push('/orders')
  } catch (e) {
    // 后端校验失败的信息同样在本页展示
    rangeError.value = e.message
  } finally {
    submitting.value = false
  }
}

// ------------------ init ------------------
onMounted(() => {
  loadMenu()
  loadCart()
  shopAPI.info()
    .then((info) => { shopInfo.value = info; if (info?.name) shopName.value = info.name })
    .catch(() => {})
})
</script>

<style scoped>
.menu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
</style>
