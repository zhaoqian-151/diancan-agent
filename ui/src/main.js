import { createApp } from 'vue'
import {
  ElAlert, ElButton, ElCheckbox, ElCol, ElDialog, ElDrawer,
  ElForm, ElFormItem, ElInput, ElInputNumber, ElOption,
  ElRadio, ElRadioGroup, ElRow, ElSelect, ElSwitch,
} from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './assets/styles/global.css'
import './assets/styles/redesign.css'
import './assets/styles/food.css'
import './assets/styles/admin.css'

const app = createApp(App)
for (const component of [
  ElAlert, ElButton, ElCheckbox, ElCol, ElDialog, ElDrawer,
  ElForm, ElFormItem, ElInput, ElInputNumber, ElOption,
  ElRadio, ElRadioGroup, ElRow, ElSelect, ElSwitch,
]) app.component(component.name, component)
app.use(router)
app.mount('#app')
