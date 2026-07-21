<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from './stores/app'
import { useProjectStore } from './stores/project'

const route = useRoute()
const app = useAppStore()
const project = useProjectStore()

const pages = computed(() => [
  ['备课项目', '/projects'],
  ['资料知识库', '/knowledge'],
  ['备课工作台', project.currentProjectId && `/workbench/${project.currentProjectId}`],
  ['质量检查', project.currentProjectId && `/quality/${project.currentProjectId}`],
  ['成果导出', project.currentProjectId && `/export/${project.currentProjectId}`],
])
const healthText = computed(
  () =>
    ({
      checking: '正在连接服务',
      online: '服务运行正常',
      offline: '后端暂不可用',
      timeout: '后端响应超时',
    })[app.backend],
)

watch(
  () => route.params.projectId,
  (id) => typeof id === 'string' && project.select(id),
  { immediate: true },
)
onMounted(app.checkHealth)
</script>

<template>
  <el-container class="shell">
    <el-aside width="236px" class="sidebar">
      <div class="brand">
        <div class="brand-mark">L</div>
        <div><b>LessonDeck</b><small>智慧备课工作台</small></div>
      </div>

      <el-menu router :default-active="route.path" class="nav">
        <el-menu-item
          v-for="([label, path], index) in pages"
          :key="label"
          :index="path || `disabled-${index}`"
          :disabled="!path"
        >
          {{ label }}
        </el-menu-item>
      </el-menu>

      <div class="sidebar-foot">
        <span :class="['health-dot', app.backend]" />{{ healthText }}
        <el-button v-if="['offline', 'timeout'].includes(app.backend)" link @click="app.checkHealth">
          重试
        </el-button>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <p class="eyebrow">面向智慧教育 · {{ route.meta.title }}</p>
          <h1>面向智慧教育的 AI 备课辅助系统</h1>
        </div>
        <nav class="top-nav">
          <RouterLink to="/projects">项目首页</RouterLink>
          <RouterLink to="/knowledge">知识库</RouterLink>
        </nav>
        <el-tag effect="plain" round>教师可控 · 来源可溯</el-tag>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.top-nav { display: flex; gap: 16px; }
.top-nav a { color: #5d6b82; text-decoration: none; }
.top-nav a.router-link-active { color: #2066d4; }
.health-dot.timeout { background: #f4b55e; }
</style>
