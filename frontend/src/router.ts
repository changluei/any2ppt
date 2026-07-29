/**
 * 页面路由与生成期全局导航锁。
 *
 * 只要 generationSession 仍处于活动状态，任何导航都会被重定向到锁定生成页，
 * 防止用户切换导航后丢失轮询与生成上下文。
 */
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
  // 生成完成/失败后 GenerationPage 会先清理 session，导航才能恢复。
  if (hasActiveGeneration() && to.path !== '/generating') return '/generating'
})
router.afterEach(to=>document.title=`${String(to.meta.title||'Any2PPT')} · Any2PPT`)
export default router
