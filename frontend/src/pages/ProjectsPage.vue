<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Delete, EditPen, MoreFilled, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import type { Project, ThemeDescriptor } from '../types'
import AppEmpty from '../components/AppEmpty.vue'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import ThemePreview from '../components/ThemePreview.vue'
import { useProjectStore } from '../stores/project'
import { workbenchPath } from '../utils/workbench'

const router = useRouter()
const projectStore = useProjectStore()
const projects = ref<Project[]>([])
const themes = ref<ThemeDescriptor[]>([])
const loading = ref(true)
const error = ref('')
const query = ref('')

const filteredProjects = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return projects.value
  return projects.value.filter((project) =>
    [project.name, project.lesson_topic, project.subject, project.grade]
      .some((value) => value.toLowerCase().includes(keyword)),
  )
})

function themeOf(project: Project) {
  return themes.value.find((theme) => theme.id === project.theme_id)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    ;[projects.value, themes.value] = await Promise.all([api.projects(), api.themes()])
  } catch (requestError) {
    error.value = (requestError as Error).message
  } finally {
    loading.value = false
  }
}

function openProject(project: Project) {
  projectStore.select(project.id)
  router.push(workbenchPath(project.id))
}

async function deleteProject(project: Project) {
  try {
    await ElMessageBox.confirm(
      `将永久删除“${project.name}”及其中的资料、图片、课件和导出文件。`,
      '删除演示',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await api.deleteProject(project.id)
    projects.value = projects.value.filter((item) => item.id !== project.id)
    if (projectStore.currentProjectId === project.id) projectStore.select('')
    ElMessage.success('演示已删除')
  } catch (requestError) {
    if (requestError !== 'cancel' && requestError !== 'close') {
      ElMessage.error((requestError as Error).message)
    }
  }
}

async function retryTheme(project: Project) {
  try {
    const updated = await api.prepareProjectTheme(project.id)
    const index = projects.value.findIndex((item) => item.id === project.id)
    if (index >= 0) projects.value[index] = updated
    ElMessage.success('主题已重新下载')
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  }
}

function handleCommand(command: string, project: Project) {
  if (command === 'edit') router.push({ path: '/create', query: { edit: project.id } })
  if (command === 'delete') deleteProject(project)
  if (command === 'retry') retryTheme(project)
}

onMounted(load)
</script>

<template>
  <section class="library-page">
    <div class="subpage-head">
      <div>
        <span class="section-number">MY PRESENTATIONS</span>
        <h1>我的演示</h1>
        <p>继续编辑最近的项目，或从新主题开始创作。</p>
      </div>
      <div class="subpage-actions">
        <el-input v-model="query" clearable placeholder="搜索演示或课题">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" size="large" :icon="Plus" @click="router.push('/create')">新建演示</el-button>
      </div>
    </div>

    <AppLoading v-if="loading" />
    <AppError v-else-if="error" :error="error" @retry="load" />
    <div v-else-if="!projects.length" class="large-empty">
      <AppEmpty text="还没有演示，先选择一个主题开始吧" />
      <el-button type="primary" @click="router.push('/create')">浏览主题</el-button>
    </div>
    <AppEmpty v-else-if="!filteredProjects.length" text="没有找到匹配的演示" />
    <div v-else class="presentation-grid">
      <article
        v-for="project in filteredProjects"
        :key="project.id"
        class="presentation-card"
        tabindex="0"
        @click="openProject(project)"
        @keyup.enter="openProject(project)"
      >
        <div class="presentation-cover">
          <ThemePreview v-if="themeOf(project)" :theme="themeOf(project)!" />
          <span class="continue-label">继续编辑 →</span>
        </div>
        <div class="presentation-copy">
          <div class="presentation-topline">
            <span>{{ project.grade }} · {{ project.subject }}</span>
            <el-dropdown trigger="click" @command="handleCommand($event, project)">
              <el-button text circle aria-label="演示操作" @click.stop><el-icon><MoreFilled /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit"><el-icon><EditPen /></el-icon>编辑信息</el-dropdown-item>
                  <el-dropdown-item v-if="project.theme_status === 'failed'" command="retry">
                    <el-icon><Refresh /></el-icon>重新下载主题
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <el-icon><Delete /></el-icon>删除演示
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <h2>{{ project.name }}</h2>
          <p>{{ project.lesson_topic }}</p>
          <div class="presentation-meta">
            <span><i :style="{ background: themeOf(project)?.palette.accent }" />{{ themeOf(project)?.name || '清晰通用' }}</span>
            <span>{{ new Date(project.updated_at).toLocaleDateString() }}</span>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
