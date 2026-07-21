<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { sourcesApi } from '../api/sources'
import type { Project, SearchResult, Source } from '../types'
import AppEmpty from '../components/AppEmpty.vue'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import StatusTag from '../components/StatusTag.vue'
import { isEmptySearch, validateSourceFile } from '../utils/files'
import { useProjectStore } from '../stores/project'

const router = useRouter()
const projectStore = useProjectStore()
const projects = ref<Project[]>([])
const projectId = ref('')
const sources = ref<Source[]>([])
const results = ref<SearchResult[]>([])
const loading = ref(true)
const sourceError = ref('')
const searchError = ref('')
const selectedFile = ref<File>()
const fileError = ref('')
const uploading = ref(false)
const progress = ref(0)
const busyId = ref('')
const query = ref('')
const topK = ref(5)
const searching = ref(false)
const searched = ref(false)
const LOW_SCORE = 0.3
let timer: number | undefined

async function loadProjects() {
  loading.value = true
  try {
    projects.value = await api.projects()
    const saved = projects.value.find(({ id }) => id === projectStore.currentProjectId)?.id
    projectId.value = saved || projects.value[0]?.id || ''
  } catch (error) {
    sourceError.value = (error as Error).message
  } finally {
    loading.value = false
  }
}

async function loadSources() {
  clearTimeout(timer)
  if (!projectId.value) return
  sourceError.value = ''
  try {
    sources.value = await sourcesApi.list(projectId.value)
    if (sources.value.some(({ status }) => ['uploaded', 'parsing', 'indexing'].includes(status))) {
      timer = window.setTimeout(loadSources, 2000)
    }
  } catch (error) {
    sourceError.value = (error as Error).message
  }
}

async function choose(file?: File) {
  if (!file || uploading.value) return
  selectedFile.value = file
  fileError.value = validateSourceFile(file) || ''
  if (fileError.value) return

  uploading.value = true
  progress.value = 0
  try {
    await sourcesApi.upload(projectId.value, file, (value) => (progress.value = value))
    ElMessage.success('上传成功，正在建立索引')
    await loadSources()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    uploading.value = false
  }
}

function pick(event: Event) {
  const input = event.target as HTMLInputElement
  choose(input.files?.[0])
  input.value = ''
}

async function changeSource(source: Source, action: 'retry' | 'remove') {
  if (action === 'remove') {
    try {
      await ElMessageBox.confirm(`确定删除“${source.original_name}”及其索引吗？`, '删除资料')
    } catch {
      return
    }
  }

  busyId.value = source.id
  try {
    if (action === 'retry') await sourcesApi.retry(projectId.value, source.id)
    else await sourcesApi.remove(projectId.value, source.id)
    ElMessage.success(action === 'retry' ? '已重新开始索引' : '资料已删除')
    await loadSources()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    busyId.value = ''
  }
}

async function search() {
  if (!query.value.trim()) return ElMessage.warning('请输入检索问题')
  searching.value = true
  searched.value = true
  searchError.value = ''
  try {
    results.value = await sourcesApi.search(projectId.value, query.value.trim(), topK.value)
    if (isEmptySearch(results.value)) ElMessage.info('没有找到相关证据，请换一种问法')
  } catch (error) {
    results.value = []
    searchError.value = (error as Error).message
  } finally {
    searching.value = false
  }
}

watch(projectId, (id) => {
  projectStore.select(id)
  results.value = []
  searched.value = false
  loadSources()
})
onMounted(loadProjects)
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h2>资料知识库</h2>
        <p>上传教材、课标或教案；检索结果保留文件名和原文位置。</p>
      </div>
      <el-select v-model="projectId" placeholder="选择备课项目" style="width: 270px">
        <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
      </el-select>
    </div>

    <AppLoading v-if="loading" />
    <AppError v-else-if="sourceError && !projects.length" :error="sourceError" @retry="loadProjects" />
    <div v-else-if="!projects.length" class="empty-project">
      <AppEmpty text="还没有备课项目，请先创建项目" />
      <el-button type="primary" @click="router.push('/projects')">前往项目首页</el-button>
    </div>

    <div v-else class="kb-grid">
      <div class="panel panel-pad">
        <label
          :class="['upload-zone', { disabled: uploading }]"
          @dragover.prevent
          @drop.prevent="choose($event.dataTransfer?.files[0])"
        >
          <input hidden type="file" accept=".pdf,.docx,.txt,.md" :disabled="uploading" @change="pick" />
          <h3>拖放或点击上传资料</h3>
          <p class="muted">支持 PDF / DOCX / TXT / Markdown，单文件不超过 20MB</p>
          <div v-if="selectedFile" class="selected-file">
            {{ selectedFile.name }} · {{ (selectedFile.size / 1024).toFixed(1) }} KB
          </div>
          <p v-if="fileError" class="file-error">{{ fileError }}</p>
          <el-progress v-if="uploading" :percentage="progress" />
        </label>

        <h3>已上传资料</h3>
        <AppError v-if="sourceError" :error="sourceError" @retry="loadSources" />
        <AppEmpty v-else-if="!sources.length" text="暂无资料" />
        <div v-for="source in sources" v-else :key="source.id" class="file-row">
          <div class="file-info">
            <b>{{ source.original_name }}</b>
            <span class="meta">
              {{ source.media_type }} · {{ (source.size / 1024).toFixed(1) }} KB ·
              {{ new Date(source.created_at).toLocaleString() }}
            </span>
            <span v-if="source.error_message" class="file-error">{{ source.error_message }}</span>
          </div>
          <StatusTag :status="source.status" />
          <el-button
            v-if="source.status === 'failed'"
            link
            :loading="busyId === source.id"
            :disabled="!!busyId"
            @click="changeSource(source, 'retry')"
          >
            重试
          </el-button>
          <el-button
            link
            type="danger"
            :loading="busyId === source.id"
            :disabled="!!busyId"
            @click="changeSource(source, 'remove')"
          >
            删除
          </el-button>
        </div>
      </div>

      <div class="panel panel-pad">
        <h3>检索测试</h3>
        <p class="muted">只展示后端从真实资料中检索到的内容。</p>
        <el-input v-model="query" type="textarea" :rows="3" placeholder="例如：本课对应的课程标准要求是什么？" />
        <div class="search-controls">
          <span>返回条数</span>
          <el-input-number v-model="topK" :min="1" :max="20" />
          <el-button
            type="primary"
            :loading="searching"
            :disabled="!sources.some(({ status }) => status === 'ready')"
            @click="search"
          >
            检索证据
          </el-button>
        </div>

        <el-alert v-if="searchError" type="error" :closable="false" :title="searchError" />
        <AppEmpty v-else-if="searched && !searching && isEmptySearch(results)" text="没有找到相关证据" />
        <div v-for="result in results" v-else :key="result.chunk_id" class="search-result">
          <b>{{ result.filename }}</b>
          <el-tag :type="result.score < LOW_SCORE ? 'warning' : 'success'" size="small">
            score {{ result.score.toFixed(3) }}{{ result.score < LOW_SCORE ? ' · 相关度较低' : '' }}
          </el-tag>
          <p>{{ result.content }}</p>
          <span class="meta">{{ result.location }} · {{ result.chunk_id }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.upload-zone { display: block; cursor: pointer; }
.upload-zone.disabled { opacity: .6; pointer-events: none; }
.selected-file { margin-top: 12px; font-weight: 600; overflow-wrap: anywhere; }
.file-error { display: block; margin-top: 5px; color: #d84c4c; font-size: 13px; }
.file-info b, .search-result p { white-space: normal; overflow-wrap: anywhere; }
.search-controls { display: flex; align-items: center; gap: 10px; margin: 12px 0; }
.search-controls .el-button { flex: 1; }
.search-result > .el-tag { float: right; }
.empty-project { text-align: center; }
</style>
