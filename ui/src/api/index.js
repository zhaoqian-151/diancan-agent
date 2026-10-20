import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('[API]', error.response?.status, error.response?.data)
    const detail = error.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map(item => item.msg).join('；')
      : error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '服务连接失败，请检查后端服务后重试'
    return Promise.reject(new Error(msg))
  },
)

// ------------------ 顾客端 ------------------

export const chatAPI = {
  sendMessage: (query, sessionId) =>
    api.post('/chat', { query, session_id: sessionId }, { timeout: 120000 }),
}

export const deliveryAPI = {
  checkRange: (address, travelMode = 2) =>
    api.post('/delivery', { address, travel_mode: travelMode }),
}

export const menuAPI = {
  getList: () => api.get('/menu/list'),
}

export const shopAPI = {
  info: () => api.get('/shop'),
}

export const cartAPI = {
  get: () => api.get('/cart'),
  add: (dishId, quantity = 1) =>
    api.post('/cart/add', { dish_id: dishId, quantity }),
  set: (dishId, quantity) =>
    api.post('/cart/set', { dish_id: dishId, quantity }),
  remove: (dishId) => api.post('/cart/remove', { dish_id: dishId }),
  clear: () => api.post('/cart/clear'),
}

export const orderAPI = {
  create: (payload) => api.post('/order', payload),
  list: (limit = 20) => api.get('/order/list', { params: { limit } }),
  detail: (orderId) => api.get(`/order/${orderId}`),
  pay: (orderId, paymentMethod, couponId) =>
    api.post(`/order/${orderId}/pay`, {
      payment_method: paymentMethod,
      coupon_id: couponId,
    }),
}

// ------------------ 会员（顾客端） ------------------

export const memberAPI = {
  lookup: (phone) => api.get('/member/lookup', { params: { phone } }),
  register: (payload) => api.post('/member/register', payload),
}

// ------------------ 餐厅端 ------------------

export const adminAPI = {
  generateDishImage: (payload) => api.post('/admin/menu/image-jobs', payload),
  dishImageJob: (jobId) => api.get(`/admin/menu/image-jobs/${jobId}`),
  orders: (status) =>
    api.get('/admin/orders', { params: status != null ? { status, limit: 200 } : { limit: 200 } }),
  updateOrderStatus: (orderId, status) =>
    api.post(`/admin/order/${orderId}/status`, { status }),
  reportSummary: () => api.get('/admin/reports/summary'),
  kitchen: () => api.get('/admin/kitchen'),
  tables: () => api.get('/admin/tables'),
  openTable: (tableNo) => api.post('/admin/table/open', { table_no: tableNo }),
  changeTable: (from, to) =>
    api.post('/admin/table/change', { from_table_no: from, to_table_no: to }),
  mergeTable: (from, to) =>
    api.post('/admin/table/merge', { from_table_no: from, to_table_no: to }),
  closeTable: (tableNo, settle = true) =>
    api.post('/admin/table/close', { table_no: tableNo, settle }),
  inventory: () => api.get('/admin/inventory'),
  updateIngredient: (ingredientId, patch) =>
    api.patch(`/admin/inventory/${ingredientId}`, patch),
  members: (keyword) =>
    api.get('/admin/members', { params: keyword ? { keyword } : {} }),
  memberDetail: (memberId) => api.get(`/admin/members/${memberId}`),
  createMember: (payload) => api.post('/admin/members', payload),
  rechargeMember: (memberId, amount) =>
    api.post(`/admin/members/${memberId}/recharge`, { amount }),
  issueCoupon: (memberId, payload) =>
    api.post(`/admin/members/${memberId}/coupons`, payload),
  createMenuItem: (payload) => api.post('/admin/menu', payload),
  updateMenuItem: (dishId, patch) =>
    api.patch(`/admin/menu/${dishId}`, patch),
}

export default api
