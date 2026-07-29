/**
 * 浏览器入口：依次注册 Pinia、路由和 Element Plus，再挂载根组件。
 * 全局样式只在这里导入，避免页面异步加载时产生重复 CSS。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import App from './App.vue'
import router from './router'
createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
