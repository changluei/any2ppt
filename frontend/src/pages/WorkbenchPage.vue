<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, Download, MagicStick, Picture, Setting } from '@element-plus/icons-vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { sourcesApi } from '../api/sources'
import { imagesApi } from '../api/images'
import type { ApiError, Artifact, ExportJob, GraphState, Project, ProjectImage, Source, Task } from '../types'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import SlidevPreview from '../components/SlidevPreview.vue'
import { useProjectStore } from '../stores/project'
import { shouldPoll, taskErrorText } from '../utils/workbench'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.projectId)
useProjectStore().select(projectId)
const project = ref<Project>()
const sources = ref<Source[]>([])
const tasks = ref<Task[]>([])
const artifacts = ref<Artifact[]>([])
const versions = ref<Artifact[]>([])
const projectImages = ref<ProjectImage[]>([])
const selectedSourceIds = ref<string[]>([])
const selectedVersionId = ref('')
const selectedSlideId = ref('')
const requirements = ref('')
const loading = ref(true)
const busy = ref('')
const error = ref<ApiError>()
const settingsVisible = ref(true)
const revisionVisible = ref(false)
const revision = ref('')
const markdownDirty = ref(false)
const imageUploading = ref(false)
const imageProgress = ref(0)
const placementVisible = ref(false)
const selectedImageId = ref('')
const imagePosition = ref<'left' | 'right' | 'center' | 'wide' | 'background'>('right')
const imageCaption = ref('')
const exportJob = ref<ExportJob>()
let timer: number | undefined

const readySources = computed(() => sources.value.filter((item) => item.status === 'ready'))
const latestTask = computed(() => tasks.value[0])
const generating = computed(() => shouldPoll(tasks.value))
const latestDeck = computed(() => artifacts.value.find((item) => item.type === 'slide_deck'))
const deck = computed(() => versions.value.find((item) => item.version_id === selectedVersionId.value) || latestDeck.value)
const slides = computed(() => deck.value?.content.slides || [])
const selectedSlide = computed(() => slides.value.find((item) => item.slide_id === selectedSlideId.value) || slides.value[0])
const canGenerate = computed(() => readySources.value.length > 0 && selectedSourceIds.value.length > 0 && !generating.value)
const currentImages = computed(() => selectedSlide.value?.images || [])
const placementOptions = [
  { value: 'left', label: '左侧' },
  { value: 'right', label: '右侧' },
  { value: 'center', label: '居中' },
  { value: 'wide', label: '下方宽图' },
  { value: 'background', label: '背景图' },
] as const

function schedule() {
  clearTimeout(timer)
  if (generating.value) timer = window.setTimeout(refresh, 1200)
}

async function loadVersions() {
  if (!latestDeck.value) {
    versions.value = []
    selectedVersionId.value = ''
    return
  }
  versions.value = await api.versions(latestDeck.value.artifact_id)
  selectedVersionId.value ||= latestDeck.value.version_id
}

async function load() {
  loading.value = true
  error.value = undefined
  try {
    ;[project.value, sources.value, tasks.value, artifacts.value, projectImages.value] = await Promise.all([
      api.project(projectId),
      sourcesApi.list(projectId),
      api.tasks(projectId),
      api.artifacts(projectId),
      imagesApi.list(projectId),
    ])
    requirements.value = project.value.teacher_requirements
    selectedSourceIds.value = readySources.value.map((item) => item.id)
    await loadVersions()
    selectedSlideId.value = slides.value[0]?.slide_id || ''
    schedule()
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    loading.value = false
  }
}

async function refresh() {
  try {
    ;[tasks.value, artifacts.value] = await Promise.all([api.tasks(projectId), api.artifacts(projectId)])
    if (!generating.value) {
      await loadVersions()
      selectedSlideId.value ||= slides.value[0]?.slide_id || ''
    }
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    schedule()
  }
}

async function generatePpt() {
  if (!canGenerate.value || busy.value) return
  busy.value = 'generate'
  error.value = undefined
  try {
    const task = await api.createTask(projectId, {
      type: 'full_lesson',
      selected_source_ids: selectedSourceIds.value,
      teacher_requirements: requirements.value,
      idempotency_key: `ppt-${crypto.randomUUID()}`,
    })
    tasks.value.unshift(task)
    ElMessage.success('正在生成 PPT')
    schedule()
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

async function waitForGraph(): Promise<GraphState> {
  let graph = await api.graph(projectId)
  if (graph.status === 'not_started') {
    const task = tasks.value.find((item) => item.type === 'full_lesson' && item.status === 'succeeded')
    graph = await api.startGraph(projectId, task?.id)
  }
  let resumed = false
  for (let index = 0; index < 80; index += 1) {
    if (graph.status === 'succeeded') return graph
    if (graph.status === 'failed' || graph.status === 'cancelled') {
      if (!graph.id || resumed) break
      graph = await api.resumeGraph(graph.id)
      resumed = true
      continue
    }
    if (graph.status === 'awaiting_confirmation' || graph.status === 'needs_revision') {
      if (!graph.id) break
      const hasBlockingIssue = graph.issues.some((item) => item.severity === 'fail')
      if (hasBlockingIssue && (graph.attempt || 1) < 3) {
        await api.confirmGraph(graph.id, 'revise')
      } else if (hasBlockingIssue) {
        throw new Error('PPT 自动检查未通过，请重新生成后再试')
      } else {
        await api.confirmGraph(graph.id, 'accept')
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
    graph = await api.graph(projectId)
  }
  return graph
}

async function downloadPpt() {
  if (!deck.value || busy.value) return
  busy.value = 'export'
  error.value = undefined
  try {
    const graph = await waitForGraph()
    if (graph.status !== 'succeeded') throw new Error('PPT 尚未准备完成，请稍后重试')
    exportJob.value = await api.createExport(projectId, 'pptx', [deck.value.version_id])
    ElMessage.info('正在使用项目模板渲染 PPT，首次导出可能需要约一分钟')
    for (let index = 0; index < 360; index += 1) {
      exportJob.value = await api.exportStatus(exportJob.value.job_id)
      if (['succeeded', 'failed'].includes(exportJob.value.status)) break
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    if (exportJob.value.status !== 'succeeded') throw new Error(exportJob.value.error_message || 'PPT 导出失败')
    const file = await api.downloadExport(exportJob.value.job_id)
    const url = URL.createObjectURL(file.blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename || `${project.value?.lesson_topic || '备课课件'}.pptx`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('PPT 已生成')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

async function saveMarkdown(markdown: string) {
  if (!latestDeck.value || !selectedSlide.value || busy.value) return
  busy.value = 'markdown'
  error.value = undefined
  try {
    const changed = await api.saveSlideMarkdown(latestDeck.value.artifact_id, {
      base_version_no: latestDeck.value.version_no,
      slide_id: selectedSlide.value.slide_id,
      markdown,
    })
    artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
    selectedVersionId.value = changed.version_id
    await loadVersions()
    markdownDirty.value = false
    ElMessage.success('Markdown 已保存并生成新版本')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

async function uploadImage(file?: File) {
  if (!file || imageUploading.value) return
  const suffix = file.name.split('.').pop()?.toLowerCase()
  if (!['png', 'jpg', 'jpeg', 'webp'].includes(suffix || '')) {
    ElMessage.warning('请选择 PNG、JPG、JPEG 或 WEBP 图片')
    return
  }
  imageUploading.value = true
  imageProgress.value = 0
  try {
    const image = await imagesApi.upload(projectId, file, (value) => (imageProgress.value = value))
    projectImages.value.unshift(image)
    selectedImageId.value = image.id
    ElMessage.success('图片已上传，可添加到任意课件页')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    imageUploading.value = false
  }
}

function pickImage(event: Event) {
  const input = event.target as HTMLInputElement
  uploadImage(input.files?.[0])
  input.value = ''
}

function openPlacement() {
  if (!projectImages.value.length) {
    ElMessage.info('请先在生成设置中上传图片')
    settingsVisible.value = true
    return
  }
  selectedImageId.value ||= projectImages.value[0].id
  imagePosition.value = 'right'
  imageCaption.value = ''
  placementVisible.value = true
}

async function placeImage() {
  if (!latestDeck.value || !selectedSlide.value || !selectedImageId.value || busy.value) return
  busy.value = 'image'
  try {
    const changed = await api.placeSlideImage(latestDeck.value.artifact_id, {
      base_version_no: latestDeck.value.version_no,
      slide_id: selectedSlide.value.slide_id,
      image_id: selectedImageId.value,
      position: imagePosition.value,
      caption: imageCaption.value,
    })
    artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
    selectedVersionId.value = changed.version_id
    await loadVersions()
    placementVisible.value = false
    ElMessage.success('图片已放入当前页')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

async function removeImage(placementId: string) {
  if (!latestDeck.value || busy.value) return
  busy.value = 'image'
  try {
    const changed = await api.removeSlideImage(
      latestDeck.value.artifact_id,
      placementId,
      latestDeck.value.version_no,
    )
    artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
    selectedVersionId.value = changed.version_id
    await loadVersions()
    ElMessage.success('图片已从当前页移除')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

function selectSlide(slideId: string) {
  if (markdownDirty.value) {
    ElMessage.warning('请先保存当前页的 Markdown 修改')
    return
  }
  selectedSlideId.value = slideId
}

async function reviseSlide() {
  if (!latestDeck.value || !selectedSlide.value || !revision.value.trim()) return
  busy.value = 'revise'
  try {
    const changed = await api.revise(latestDeck.value.artifact_id, {
      base_version_no: latestDeck.value.version_no,
      target_type: 'slide',
      target_id: selectedSlide.value.slide_id,
      instruction: revision.value.trim(),
      sync_related: true,
    })
    artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
    selectedVersionId.value = changed.version_id
    revision.value = ''
    revisionVisible.value = false
    await loadVersions()
    ElMessage.success('当前页已更新')
  } catch (requestError) {
    error.value = requestError as ApiError
  } finally {
    busy.value = ''
  }
}

watch(deck, () => {
  if (!slides.value.some((item) => item.slide_id === selectedSlideId.value)) {
    selectedSlideId.value = slides.value[0]?.slide_id || ''
  }
})
function confirmLeave() {
  return !markdownDirty.value || window.confirm('当前页的 Markdown 修改尚未保存，确定离开吗？')
}
function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!markdownDirty.value) return
  event.preventDefault()
}
onBeforeRouteLeave(confirmLeave)
onMounted(load)
onMounted(() => window.addEventListener('beforeunload', handleBeforeUnload))
onUnmounted(() => {
  clearTimeout(timer)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <AppLoading v-if="loading" />
  <AppError v-else-if="error && !project" :error="error.message" @retry="load" />
  <section v-else-if="project" class="project-workbench">
    <header class="project-hero">
      <div class="project-title">
        <el-button text circle aria-label="返回项目列表" @click="router.push('/projects')"><el-icon><ArrowLeft /></el-icon></el-button>
        <div><p>{{ project.grade }} · {{ project.subject }}</p><h2>{{ project.lesson_topic }}</h2></div>
      </div>
      <div class="project-actions">
        <el-button :icon="Setting" @click="settingsVisible = !settingsVisible">生成设置</el-button>
        <el-button type="primary" :icon="MagicStick" :loading="generating || busy === 'generate'" :disabled="!canGenerate || !!busy || markdownDirty" @click="generatePpt">
          {{ latestDeck ? '重新生成 PPT' : '生成 PPT' }}
        </el-button>
        <el-button type="success" :icon="Download" :loading="busy === 'export'" :disabled="!deck || generating || !!busy || markdownDirty" @click="downloadPpt">导出 PPT</el-button>
      </div>
    </header>

    <el-alert v-if="error" type="error" :closable="true" class="workbench-alert" @close="error = undefined">
      <template #title>{{ taskErrorText(error.code, error.message) }}</template>
    </el-alert>

    <div :class="['ppt-workspace',{compact:!settingsVisible}]">
      <aside v-if="settingsVisible" class="panel setup-panel">
        <div class="setup-section">
          <div class="section-heading"><h3>参考资料</h3><el-button link @click="router.push('/knowledge')">管理资料</el-button></div>
          <el-checkbox-group v-if="readySources.length" v-model="selectedSourceIds" class="source-list">
            <el-checkbox v-for="source in readySources" :key="source.id" :value="source.id" :label="source.id">{{ source.original_name }}</el-checkbox>
          </el-checkbox-group>
          <el-empty v-else :image-size="52" description="知识库中暂无可用资料" />
        </div>
        <div class="setup-section">
          <h3>补充要求</h3>
          <el-input v-model="requirements" type="textarea" :rows="5" maxlength="1000" placeholder="例如：突出生活情境，控制在 40 分钟" />
          <p class="setup-tip">这里填写内容与教学要求；课件风格沿用创建项目时选择的模板。</p>
        </div>
        <div class="setup-section">
          <div class="section-heading">
            <h3>课件图片</h3>
            <label class="image-upload-button">
              <input hidden type="file" accept=".png,.jpg,.jpeg,.webp" :disabled="imageUploading" @change="pickImage" />
              <el-button link type="primary" :loading="imageUploading" :icon="Picture">上传图片</el-button>
            </label>
          </div>
          <el-progress v-if="imageUploading" :percentage="imageProgress" />
          <div v-if="projectImages.length" class="image-library">
            <div v-for="image in projectImages" :key="image.id" class="image-thumb" :title="image.original_name">
              <img :src="imagesApi.url(image.id)" :alt="image.original_name" />
              <span>{{ image.original_name }}</span>
            </div>
          </div>
          <p v-else class="setup-tip">上传本地图片后，可在任意课件页选择位置。</p>
        </div>
        <div v-if="deck?.content.theme_name" class="theme-match">
          <span>项目模板</span>
          <b>{{ deck.content.theme_name }}</b>
          <p>{{ deck.content.theme_description }}</p>
          <small>{{ deck.content.theme_match_reason }} · 已按模板版式生成</small>
        </div>
        <div v-if="latestTask" class="generation-state">
          <span>{{ generating ? '正在生成课件' : latestTask.status === 'failed' ? '生成失败' : '最近一次生成已完成' }}</span>
          <el-progress :percentage="latestTask.progress" :status="latestTask.status === 'failed' ? 'exception' : latestTask.status === 'succeeded' ? 'success' : undefined" />
        </div>
      </aside>

      <main class="panel deck-panel">
        <template v-if="deck && slides.length">
          <div class="deck-toolbar">
            <div><b>{{ deck.content.deck_title || project.lesson_topic }}</b><span>{{ slides.length }} 页</span><el-tag v-if="deck.content.theme_name" size="small" effect="plain">{{ deck.content.theme_name }}</el-tag></div>
            <el-select v-if="versions.length > 1" v-model="selectedVersionId" size="small" style="width:150px" :disabled="markdownDirty">
              <el-option v-for="item in versions" :key="item.version_id" :label="`版本 ${item.version_no}`" :value="item.version_id" />
            </el-select>
          </div>
          <div class="deck-content">
            <nav class="slide-rail" aria-label="PPT 页面">
              <button v-for="slide in slides" :key="slide.slide_id" :class="{active:selectedSlide?.slide_id === slide.slide_id}" @click="selectSlide(slide.slide_id)">
                <span>{{ slide.order }}</span><b>{{ slide.title }}</b>
              </button>
            </nav>
            <div class="slide-canvas">
              <SlidevPreview
                :key="selectedSlide?.slide_id"
                :title="selectedSlide?.title"
                :markdown="selectedSlide?.markdown || ''"
                :images="selectedSlide?.images || []"
                :image-base-url="imagesApi.baseUrl()"
                :theme-palette="deck.content.theme_palette"
                :saving="busy === 'markdown'"
                @save="saveMarkdown"
                @dirty-change="markdownDirty = $event"
              />
              <div class="slide-actions">
                <span>第 {{ selectedSlide?.order }} 页 / 共 {{ slides.length }} 页</span>
                <div>
                  <el-button text type="primary" :icon="Picture" :disabled="markdownDirty || !!busy" @click="openPlacement">添加图片</el-button>
                  <el-button text type="primary" :disabled="markdownDirty" @click="revisionVisible = true">用要求调整当前页</el-button>
                </div>
              </div>
              <div v-if="currentImages.length" class="current-images">
                <span>本页图片</span>
                <el-tag v-for="image in currentImages" :key="image.placement_id" closable :disable-transitions="true" @close="removeImage(image.placement_id)">
                  {{ image.original_name }} · {{ placementOptions.find(item => item.value === image.position)?.label }}
                </el-tag>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="deck-empty">
          <div class="empty-mark">PPT</div>
          <h2>从资料生成完整课件</h2>
          <p>教学设计、课堂活动、讲解提示和练习会自动整理到同一份 PPT 中。</p>
          <el-button type="primary" size="large" :disabled="!canGenerate" @click="generatePpt">开始生成</el-button>
        </div>
      </main>
    </div>

    <el-dialog v-model="revisionVisible" title="调整当前页" width="520px">
      <p class="muted">{{ selectedSlide?.title }}</p>
      <el-input v-model="revision" type="textarea" :rows="5" maxlength="1000" placeholder="描述你希望如何修改这一页" />
      <template #footer><el-button @click="revisionVisible = false">取消</el-button><el-button type="primary" :loading="busy === 'revise'" @click="reviseSlide">应用修改</el-button></template>
    </el-dialog>

    <el-dialog v-model="placementVisible" title="添加图片到当前页" width="680px">
      <div class="placement-form">
        <h4>选择图片</h4>
        <div class="placement-images">
          <button v-for="image in projectImages" :key="image.id" :class="{active:selectedImageId === image.id}" @click="selectedImageId = image.id">
            <img :src="imagesApi.url(image.id)" :alt="image.original_name" />
            <span>{{ image.original_name }}</span>
          </button>
        </div>
        <h4>放置位置</h4>
        <el-radio-group v-model="imagePosition">
          <el-radio-button v-for="item in placementOptions" :key="item.value" :value="item.value">{{ item.label }}</el-radio-button>
        </el-radio-group>
        <el-input v-model="imageCaption" maxlength="300" placeholder="图片说明（可选）" />
      </div>
      <template #footer>
        <el-button @click="placementVisible = false">取消</el-button>
        <el-button type="primary" :icon="Picture" :loading="busy === 'image'" :disabled="!selectedImageId" @click="placeImage">放入当前页</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.project-workbench{max-width:1600px;margin:0 auto}.project-hero{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px}.project-title,.project-actions,.section-heading,.deck-toolbar,.slide-actions{display:flex;align-items:center}.project-title{gap:8px}.project-title p{margin:0 0 4px;color:#7a8499;font-size:13px}.project-title h2{margin:0;font-size:25px}.project-actions{gap:10px}.workbench-alert{margin-bottom:14px}.ppt-workspace{display:grid;grid-template-columns:290px minmax(0,1fr);gap:16px;min-height:650px}.ppt-workspace.compact{grid-template-columns:1fr}.setup-panel{padding:20px;max-height:750px;overflow:auto}.setup-section+ .setup-section{margin-top:24px}.setup-section h3{margin:0 0 12px;font-size:15px}.section-heading{justify-content:space-between}.setup-tip{margin:8px 0 0;color:#8993a5;font-size:12px;line-height:1.5}.source-list{display:grid;gap:8px}.source-list :deep(.el-checkbox){height:auto;margin-right:0;align-items:flex-start}.source-list :deep(.el-checkbox__label){white-space:normal;overflow-wrap:anywhere;line-height:1.4}.image-upload-button{cursor:pointer}.image-library{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.image-thumb{min-width:0}.image-thumb img{width:100%;aspect-ratio:1.3;object-fit:cover;border-radius:8px;border:1px solid #e1e5ed}.image-thumb span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;color:#758096}.theme-match{margin-top:24px;padding:13px;border:1px solid #e2e5f2;border-radius:11px;background:#f7f7fd}.theme-match span,.theme-match b{display:block}.theme-match span{font-size:11px;color:#838ca1}.theme-match b{margin-top:3px;font-size:14px;color:#4652a6}.theme-match p{margin:7px 0;color:#667085;font-size:12px;line-height:1.5}.theme-match small{color:#9299aa}.generation-state{margin-top:20px;padding:14px;border-radius:12px;background:#f5f6fb;color:#59647a;font-size:13px}.generation-state .el-progress{margin-top:10px}.deck-panel{overflow:hidden}.deck-toolbar{height:58px;justify-content:space-between;padding:0 18px;border-bottom:1px solid #eceef4}.deck-toolbar span{margin-left:10px;color:#8a93a5;font-size:13px}.deck-toolbar .el-tag{margin-left:10px}.deck-content{display:grid;grid-template-columns:190px minmax(0,1fr);height:650px}.slide-rail{padding:12px;background:#f7f8fc;overflow:auto}.slide-rail button{width:100%;display:grid;grid-template-columns:24px 1fr;gap:7px;align-items:start;padding:10px;margin-bottom:7px;border:1px solid transparent;border-radius:9px;background:transparent;text-align:left;color:#697386;cursor:pointer}.slide-rail button:hover{background:#fff}.slide-rail button.active{background:#fff;border-color:#cfd5f9;color:#4051c7;box-shadow:0 3px 12px rgba(72,85,180,.08)}.slide-rail button span{font-size:11px}.slide-rail button b{font-size:12px;line-height:1.35}.slide-canvas{min-width:0;padding:22px 26px;background:#eef0f6;overflow:auto}.slide-actions{justify-content:space-between;margin-top:8px;color:#7a8498;font-size:12px}.current-images{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:7px;color:#7a8498;font-size:12px}.placement-form h4{margin:18px 0 10px}.placement-form h4:first-child{margin-top:0}.placement-images{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;max-height:260px;overflow:auto}.placement-images button{padding:6px;border:2px solid transparent;border-radius:10px;background:#f5f6fa;cursor:pointer;text-align:left}.placement-images button.active{border-color:#6370d8;background:#f0f1ff}.placement-images img{display:block;width:100%;aspect-ratio:1.45;object-fit:cover;border-radius:6px}.placement-images span{display:block;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.placement-form .el-input{margin-top:16px}.deck-empty{height:100%;min-height:620px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px}.deck-empty p{max-width:540px;color:#7c8699;line-height:1.7}.empty-mark{display:grid;place-items:center;width:78px;height:78px;border-radius:24px;background:#eef0ff;color:#5968d8;font-size:20px;font-weight:800;letter-spacing:1px}@media(max-width:1100px){.project-hero{align-items:flex-start;flex-direction:column}.ppt-workspace{grid-template-columns:250px minmax(0,1fr)}.deck-content{grid-template-columns:150px minmax(0,1fr)}}@media(max-width:820px){.ppt-workspace{display:block}.setup-panel{margin-bottom:14px}.deck-content{grid-template-columns:1fr;height:auto}.slide-rail{display:flex;gap:6px;overflow:auto}.slide-rail button{min-width:130px}.project-actions{flex-wrap:wrap}.placement-images{grid-template-columns:repeat(2,1fr)}}
</style>
