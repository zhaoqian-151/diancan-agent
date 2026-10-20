import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/admin', name: 'admin-dashboard', component: () => import('../views/AdminDashboard.vue'), meta: { title: '经营总览' } },
  {
    path: '/',
    name: 'home',
    component: () => import('../views/Home.vue'),
    meta: { title: '点餐' },
  },
  {
    path: '/orders',
    name: 'orders',
    component: () => import('../views/OrderList.vue'),
    meta: { title: '我的订单' },
  },
  {
    path: '/admin/orders',
    name: 'admin-orders',
    component: () => import('../views/AdminOrders.vue'),
    meta: { title: '餐厅·订单管理' },
  },
  {
    path: '/admin/menu',
    name: 'admin-menu',
    component: () => import('../views/AdminMenu.vue'),
    meta: { title: '餐厅·菜品管理' },
  },
  {
    path: '/admin/reports',
    name: 'admin-reports',
    component: () => import('../views/AdminReports.vue'),
    meta: { title: '餐厅·经营数据' },
  },
  {
    path: '/admin/tables',
    name: 'admin-tables',
    component: () => import('../views/AdminTables.vue'),
    meta: { title: '餐厅·桌台管理' },
  },
  {
    path: '/admin/inventory',
    name: 'admin-inventory',
    component: () => import('../views/AdminInventory.vue'),
    meta: { title: '餐厅·库存管理' },
  },
  {
    path: '/admin/members',
    name: 'admin-members',
    component: () => import('../views/AdminMembers.vue'),
    meta: { title: '餐厅·会员管理' },
  },
  {
    path: '/kitchen',
    name: 'kitchen',
    component: () => import('../views/KitchenScreen.vue'),
    meta: { title: '后厨大屏' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.afterEach((to) => {
  if (to.meta?.title) {
    document.title = `${to.meta.title} · 智能点餐`
  }
})

export default router
