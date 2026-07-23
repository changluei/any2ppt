<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Collection, Expand, Fold, FolderOpened } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const collapsed = ref(localStorage.getItem('sidebar-collapsed') === 'true')
const pages = [
  { label: '备课项目', path: '/projects', icon: FolderOpened },
  { label: '知识库', path: '/knowledge', icon: Collection },
]
const activePage = computed(() => route.path.startsWith('/workbench') ? '/projects' : route.path)

watch(collapsed, (value) => localStorage.setItem('sidebar-collapsed', String(value)))
</script>

<template>
  <el-container :class="['shell',{collapsed}]">
    <el-aside :width="collapsed ? '72px' : '208px'" class="sidebar">
      <div v-if="!collapsed" class="sidebar-title">AI 备课助手</div>
      <el-menu router :default-active="activePage" :collapse="collapsed" class="nav">
        <el-menu-item v-for="page in pages" :key="page.path" :index="page.path">
          <el-icon><component :is="page.icon" /></el-icon>
          <template #title>{{ page.label }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="content-shell">
      <el-header class="topbar">
        <div class="topbar-left">
          <el-button text circle :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed">
            <el-icon size="20"><Expand v-if="collapsed" /><Fold v-else /></el-icon>
          </el-button>
          <div>
            <p class="eyebrow">{{ route.meta.title }}</p>
            <h1>{{ route.path.startsWith('/workbench') ? '项目工作台' : 'AI 备课辅助系统' }}</h1>
          </div>
        </div>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.content-shell{margin-left:208px;transition:margin-left .22s ease}.shell.collapsed .content-shell{margin-left:72px}
.sidebar-title{height:72px;display:flex;align-items:center;padding:0 22px;font-size:16px;font-weight:700;color:#26324b;white-space:nowrap}
.topbar-left{display:flex;align-items:center;gap:12px}.topbar-left h1{font-size:18px}
</style>
