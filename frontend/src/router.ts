import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  {path:'/',redirect:'/projects'},
  {path:'/projects',component:()=>import('./pages/ProjectsPage.vue'),meta:{title:'备课项目'}},
  {path:'/knowledge',component:()=>import('./pages/KnowledgePage.vue'),meta:{title:'知识库'}},
  {path:'/workbench/:projectId',component:()=>import('./pages/WorkbenchPage.vue'),meta:{title:'备课项目'}},
]
const router=createRouter({history:createWebHistory(),routes})
router.afterEach(to=>document.title=`${String(to.meta.title||'')} · AI 备课辅助系统`)
export default router
