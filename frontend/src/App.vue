<script setup lang="ts">
import { onMounted } from 'vue'; import { useAppStore } from './stores/app'; import { FolderOpened, Collection, MagicStick } from '@element-plus/icons-vue'
const store=useAppStore(); onMounted(()=>store.checkHealth())
</script>
<template><el-container class="shell"><el-aside width="236px" class="sidebar">
  <div class="brand"><div class="brand-mark">L</div><div><b>LessonDeck</b><small>智慧备课工作台</small></div></div>
  <el-menu router :default-active="$route.path" class="nav"><el-menu-item index="/projects"><el-icon><FolderOpened/></el-icon><span>备课项目</span></el-menu-item><el-menu-item index="/knowledge"><el-icon><Collection/></el-icon><span>资料知识库</span></el-menu-item></el-menu>
  <div class="sidebar-foot"><span :class="['health-dot',store.backend]"></span>{{store.backend==='online'?'服务运行正常':store.backend==='checking'?'正在连接服务':'后端暂不可用'}}<el-button v-if="store.backend==='offline'" link @click="store.checkHealth">重试</el-button></div>
</el-aside><el-container><el-header class="topbar"><div><p class="eyebrow">面向智慧教育</p><h1>AI 备课辅助系统</h1></div><el-tag effect="plain" round><el-icon><MagicStick/></el-icon> 教师可控 · 来源可溯</el-tag></el-header><el-main><router-view/></el-main></el-container></el-container></template>

