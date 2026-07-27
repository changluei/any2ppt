import { createRouter, createWebHistory } from 'vue-router'
import { hasActiveGeneration } from './services/generationSession'
const routes = [
  { path: '/', redirect: '/create' },
  { path: '/create', component: () => import('./pages/CreatePage.vue'), meta: { title: '创建演示' } },
  { path: '/projects', component: () => import('./pages/ProjectsPage.vue'), meta: { title: '我的演示' } },
  { path: '/knowledge', component: () => import('./pages/KnowledgePage.vue'), meta: { title: '知识库' } },
  { path: '/generating', component: () => import('./pages/GenerationPage.vue'), meta: { title: '正在生成', fullScreen: true } },
  { path: '/workbench/:projectId', component: () => import('./pages/WorkbenchPage.vue'), meta: { title: '编辑演示' } },
]
const router=createRouter({history:createWebHistory(),routes})
router.beforeEach(to => {
  if (hasActiveGeneration() && to.path !== '/generating') return '/generating'
})
router.afterEach(to=>document.title=`${String(to.meta.title||'Any2PPT')} · Any2PPT`)
export default router
