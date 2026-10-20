<template>
  <div class="app-shell" :class="{ 'nav-open': navOpen, 'dining-mode': !isAdmin, 'admin-mode': isAdmin }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <button v-if="navOpen" class="nav-scrim" aria-label="关闭菜单" @click="navOpen = false"></button>
    <aside class="app-sidebar">
      <router-link to="/" class="brand"><span class="brand-mark"><AppIcon name="bowl" :size="26" /></span><span>知味<span class="brand-en">SMART DINING</span></span></router-link>
      <div class="workspace-switch"><router-link to="/" :class="{ selected: !isAdmin }">顾客点餐</router-link><router-link to="/admin" :class="{ selected: isAdmin }">餐厅经营</router-link></div>
      <nav aria-label="主要导航"><template v-for="group in groups" :key="group.label"><div class="nav-group-label">{{ group.label }}</div><router-link v-for="item in group.items" :key="item.to" :to="item.to" class="sidebar-link" :class="{ selected: route.path === item.to }"><AppIcon :name="item.icon" /><span>{{ item.label }}</span><AppIcon v-if="route.path === item.to" name="chevron" :size="15" /></router-link></template></nav>
      <div class="sidebar-bottom"><div class="sidebar-note"><AppIcon name="leaf" :size="18" /><span>每一餐，都值得用心</span></div><div class="workspace-caption">单店餐饮工作空间 <span>v2.0</span></div></div>
    </aside>
    <div class="app-content"><header class="workspace-header"><div class="breadcrumbs"><button class="mobile-nav btn-ghost btn-sm" aria-label="打开导航" @click="navOpen = !navOpen"><AppIcon name="bars" /></button><span>{{ isAdmin ? '餐厅工作台' : '美好食光' }}</span><AppIcon name="chevron" :size="13" /><strong>{{ route.meta.title }}</strong></div><div class="header-right"><span class="local-badge">{{ isAdmin ? '本地工作空间' : '欢迎用餐' }}</span><span class="header-avatar">{{ isAdmin ? '店' : '客' }}</span></div></header>
      <main id="main-content" tabindex="-1"><router-view /></main><footer class="app-footer"><span>知味 · 智能点餐</span><span>用真实数据，照顾每一份好味道</span></footer>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
const route = useRoute()
const navOpen = ref(false)
const isAdmin = computed(() => route.path.startsWith('/admin') || route.path === '/kitchen')
watch(isAdmin, active => { document.documentElement.dataset.workspace = active ? 'admin' : 'dining' }, { immediate: true })
const groups = computed(() => isAdmin.value ? [
  { label: '工作空间', items: [{ to: '/admin', label: '经营总览', icon: 'grid' }] },
  { label: '营业管理', items: [{ to: '/admin/orders', label: '订单管理', icon: 'orders' }, { to: '/kitchen', label: '后厨工作台', icon: 'chef' }, { to: '/admin/tables', label: '桌台管理', icon: 'table' }] },
  { label: '商品与经营', items: [{ to: '/admin/menu', label: '菜品管理', icon: 'menu' }, { to: '/admin/inventory', label: '原料库存', icon: 'box' }, { to: '/admin/members', label: '会员管理', icon: 'users' }, { to: '/admin/reports', label: '经营报表', icon: 'chart' }] },
] : [{ label: '用餐服务', items: [{ to: '/', label: '发现好味', icon: 'bowl' }, { to: '/orders', label: '我的订单', icon: 'orders' }] }])
watch(() => route.path, () => { navOpen.value = false })
</script>
