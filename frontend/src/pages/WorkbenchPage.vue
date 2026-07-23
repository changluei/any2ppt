<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { sourcesApi } from '../api/sources'
import type { ApiError, Artifact, ArtifactType, Citation, Project, Skill, Source, Task } from '../types'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import StatusTag from '../components/StatusTag.vue'
import { shouldPoll } from '../utils/workbench'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.projectId)
const project = ref<Project>()
const skills = ref<Skill[]>([])
const sources = ref<Source[]>([])
const tasks = ref<Task[]>([])
const artifacts = ref<Artifact[]>([])
const selectedSourceIds = ref<string[]>([])
const requirements = ref('')
const loading = ref(true)
const pageError = ref('')
const actionError = ref<ApiError>()
const busy = ref('')
const activeType = ref<ArtifactType>('lesson_plan')
const selectedSlide = ref('')
const selectedCitation = ref<Citation>()
const drawerVisible = ref(false)
const exerciseView = ref('教师视图')
const revision = ref('')
const sync = ref(true)
let timer: number | undefined

const readySources = computed(() => sources.value.filter(({ status }) => status === 'ready'))
const running = computed(() => shouldPoll(tasks.value))
const artifact = computed(() => artifacts.value.find(({ type }) => type === activeType.value))
const deck = computed(() => artifacts.value.find(({ type }) => type === 'slide_deck'))
const notes = computed(() => artifacts.value.find(({ type }) => type === 'speaker_notes'))
const selected = computed(() => deck.value?.content.slides?.find(({ slide_id }) => slide_id === selectedSlide.value))
const selectedNote = computed(() => notes.value?.content.notes?.find(({ slide_id }) => slide_id === selectedSlide.value))
const inputNames: Record<string, string> = {
  lesson_topic: '课题', grade: '年级', student_profile: '学情', lesson_count: '课时数',
}

function stopPolling() {
  clearTimeout(timer)
  timer = undefined
}

function schedulePolling() {
  stopPolling()
  if (shouldPoll(tasks.value)) timer = window.setTimeout(refreshTasks, 1500)
}

async function load() {
  loading.value = true
  pageError.value = ''
  try {
    const rows = await Promise.all([
      api.project(projectId), api.skills(), sourcesApi.list(projectId), api.tasks(projectId), api.artifacts(projectId),
    ])
    ;[project.value, skills.value, sources.value, tasks.value, artifacts.value] = rows
    requirements.value = project.value.teacher_requirements
    selectedSourceIds.value = readySources.value.map(({ id }) => id)
    selectedSlide.value ||= deck.value?.content.slides?.[0]?.slide_id || ''
    schedulePolling()
  } catch (error) {
    pageError.value = (error as Error).message
  } finally {
    loading.value = false
  }
}

async function refreshTasks() {
  try {
    ;[tasks.value, artifacts.value] = await Promise.all([api.tasks(projectId), api.artifacts(projectId)])
    selectedSlide.value ||= deck.value?.content.slides?.[0]?.slide_id || ''
  } catch (error) {
    actionError.value = error as ApiError
  } finally {
    schedulePolling()
  }
}

async function runSkill(type: string) {
  if (busy.value || running.value) return
  if (!selectedSourceIds.value.length) return ElMessage.warning('请先选择至少一份已就绪资料')
  busy.value = 'create'
  actionError.value = undefined
  try {
    const task = await api.createTask(projectId, {
      type,
      selected_source_ids: selectedSourceIds.value,
      teacher_requirements: requirements.value,
      idempotency_key: `${type}-${crypto.randomUUID()}`,
    })
    tasks.value.unshift(task)
    ElMessage.success('任务已创建')
    schedulePolling()
  } catch (error) {
    actionError.value = error as ApiError
  } finally {
    busy.value = ''
  }
}

async function changeTask(task: Task, action: 'cancel' | 'retry') {
  if (busy.value) return
  busy.value = task.id
  actionError.value = undefined
  try {
    const changed = action === 'cancel' ? await api.cancelTask(task.id) : await api.retryTask(task.id)
    tasks.value = [changed, ...tasks.value.filter(({ id }) => id !== changed.id)]
    ElMessage.success(action === 'cancel' ? '任务已取消' : '任务已重新创建')
    schedulePolling()
  } catch (error) {
    actionError.value = error as ApiError
  } finally {
    busy.value = ''
  }
}

async function copyTrace(traceId: string) {
  await navigator.clipboard.writeText(traceId)
  ElMessage.success('trace_id 已复制')
}

async function reviseArtifact() {
  if (!artifact.value || !revision.value.trim()) return
  const targetType = activeType.value === 'slide_deck' ? 'slide' : activeType.value === 'speaker_notes' ? 'note' : activeType.value === 'exercise_set' ? 'exercise' : 'stages'
  const targetId = activeType.value === 'lesson_plan' ? artifact.value.content.stages?.[0]?.id || '' : selectedSlide.value
  busy.value = 'revise'
  try {
    const changed = await api.revise(artifact.value.artifact_id, {
      base_version_no: artifact.value.version_no, target_type: targetType, target_id: targetId,
      instruction: revision.value, sync_related: sync.value,
    })
    artifacts.value = artifacts.value.map((item) => item.artifact_id === changed.artifact_id ? changed : item)
    revision.value = ''
    ElMessage.success(`已保存为 v${changed.version_no}`)
  } catch (error) {
    actionError.value = error as ApiError
  } finally {
    busy.value = ''
  }
}

function showCitation(citation: Citation) {
  selectedCitation.value = citation
  drawerVisible.value = true
}

onMounted(load)
onUnmounted(stopPolling)
</script>

<template>
  <AppLoading v-if="loading" />
  <AppError v-else-if="pageError" :error="pageError" @retry="load" />
  <section v-else-if="project">
    <div class="page-head">
      <div><h2>{{ project.lesson_topic }}</h2><p>{{ project.grade }} · {{ project.subject }} · {{ project.textbook_version || '未指定教材版本' }}</p></div>
      <div>
        <el-button @click="router.push(`/knowledge`)">管理资料</el-button>
        <el-button @click="router.push(`/quality/${projectId}`)">质量检查</el-button>
        <el-button type="primary" :loading="busy === 'create'" :disabled="running || !!busy" @click="runSkill('full_lesson')">生成完整备课包</el-button>
      </div>
    </div>

    <el-alert v-if="actionError" type="error" :closable="false" class="action-error">
      <template #title>
        {{ actionError.message }}
        <el-button v-if="actionError.traceId" link type="danger" @click="copyTrace(actionError.traceId)">复制 trace_id</el-button>
      </template>
    </el-alert>

    <div class="workbench">
      <aside class="panel work-col context-box">
        <p class="eyebrow">课程输入</p><h3>{{ project.name }}</h3>
        <p class="muted">{{ project.student_profile || '尚未填写学情特点' }}</p>
        <el-input v-model="requirements" type="textarea" :rows="2" placeholder="本次生成的补充要求" maxlength="3000" />
        <el-divider />

        <p class="eyebrow">已就绪资料</p>
        <el-checkbox-group v-if="readySources.length" v-model="selectedSourceIds" class="source-options">
          <el-checkbox v-for="source in readySources" :key="source.id" :label="source.id">{{ source.original_name }}</el-checkbox>
        </el-checkbox-group>
        <div v-else class="muted">暂无可用资料，请先到知识库上传并等待索引完成。</div>
        <el-divider />

        <p class="eyebrow">五类教学 Skills</p>
        <div v-for="skill in skills" :key="skill.id" class="skill-card">
          <b>{{ skill.name }}</b><p class="meta">{{ skill.description }}</p>
          <small>需要：{{ skill.required_inputs.map((item) => inputNames[item] || item).join('、') }}</small>
          <el-button link type="primary" :disabled="running || !!busy" @click="runSkill(skill.id)">运行此 Skill →</el-button>
        </div>

        <el-divider /><p class="eyebrow">最近任务</p>
        <div v-if="!tasks.length" class="muted">尚未发起任务</div>
        <div v-for="task in tasks.slice(0, 5)" :key="task.id" class="task-row">
          <div><StatusTag :status="task.status" /> <span class="meta">{{ task.stage }} · {{ task.progress }}%</span></div>
          <el-progress v-if="task.status === 'running'" :percentage="task.progress" :show-text="false" />
          <p v-if="task.error_message" class="task-error">{{ task.error_message }}</p>
          <el-button v-if="['pending','running'].includes(task.status)" link :disabled="!!busy" @click="changeTask(task, 'cancel')">取消</el-button>
          <el-button v-if="['failed','cancelled'].includes(task.status)" link :disabled="!!busy" @click="changeTask(task, 'retry')">重试</el-button>
          <el-button v-if="task.trace_id" link @click="copyTrace(task.trace_id)">复制 trace_id</el-button>
        </div>
      </aside>

      <main class="panel work-col artifact-area">
        <el-tabs v-model="activeType">
          <el-tab-pane label="教学设计" name="lesson_plan" /><el-tab-pane label="课件" name="slide_deck" />
          <el-tab-pane label="讲稿" name="speaker_notes" /><el-tab-pane label="练习" name="exercise_set" />
        </el-tabs>
        <el-empty v-if="!artifact" description="选择左侧资料和 Skill 后，真实产物会显示在这里" />
        <template v-else>
          <div v-for="warning in artifact.warnings" :key="warning" class="warning">{{ warning }}</div>
          <template v-if="activeType === 'lesson_plan'">
            <h2>{{ artifact.content.title }}</h2><h3>教学目标</h3>
            <div v-for="item in artifact.content.objectives || []" :key="item.id" class="notes-card"><el-tag>{{ item.id }}</el-tag> {{ item.behavior }}<p class="meta">条件：{{ item.condition }} · 标准：{{ item.criterion }}</p></div>
            <h3>课堂流程</h3><el-timeline><el-timeline-item v-for="item in artifact.content.stages || []" :key="item.id" :timestamp="`${item.time_minutes} 分钟`"><b>{{ item.name }}</b><p>教师：{{ item.teacher_actions }}</p><p>学生：{{ item.student_actions }}</p></el-timeline-item></el-timeline>
          </template>
          <template v-else-if="activeType === 'slide_deck'">
            <div class="row"><div class="slide-list"><div v-for="item in artifact.content.slides || []" :key="item.slide_id" :class="['slide-thumb',{active:selectedSlide === item.slide_id}]" @click="selectedSlide = item.slide_id"><b>{{ item.order }}. {{ item.title }}</b><br>{{ item.teaching_stage }}</div></div>
              <div class="grow"><div class="slide-stage"><h1>{{ selected?.title }}</h1><p>{{ selected?.markdown }}</p></div><div v-if="selectedNote" class="notes-card"><b>同步讲稿</b><p>{{ selectedNote.explanation }}</p><span class="meta">{{ selectedNote.transition }}</span></div></div></div>
          </template>
          <template v-else-if="activeType === 'speaker_notes'">
            <div v-for="item in artifact.content.notes || []" :key="item.slide_id" class="notes-card" @click="selectedSlide = item.slide_id"><el-tag>{{ item.slide_id }}</el-tag><p>{{ item.explanation }}</p><b>课堂提问</b><ul><li v-for="question in item.questions" :key="question">{{ question }}</li></ul><span class="meta">过渡：{{ item.transition }} · 板书：{{ item.board_notes }}</span></div>
          </template>
          <template v-else>
            <el-segmented v-model="exerciseView" :options="['教师视图','学生预览']" />
            <div v-for="item in artifact.content.exercises || []" :key="item.exercise_id" class="notes-card" @click="selectedSlide = item.exercise_id"><el-tag>{{ item.level }}</el-tag> <b>{{ item.question }}</b><template v-if="exerciseView === '教师视图'"><p>答案：{{ item.answer }}</p><p class="meta">解析：{{ item.explanation }}</p></template><el-tag v-if="item.needs_teacher_review && exerciseView === '教师视图'" type="warning">需教师确认</el-tag></div>
          </template>
          <el-divider /><h3>局部修改当前内容</h3>
          <el-input v-model="revision" type="textarea" placeholder="请输入修改要求" maxlength="1000" />
          <el-checkbox v-model="sync">同步关联讲稿/练习</el-checkbox>
          <el-button type="primary" plain :loading="busy === 'revise'" :disabled="!!busy" @click="reviseArtifact">保存为新版本</el-button>
        </template>
      </main>

      <aside class="panel work-col context-box">
        <el-tabs>
          <el-tab-pane label="来源">
            <span v-for="citation in artifact?.citations || []" :key="citation.chunk_id" class="citation" @click="showCitation(citation)"><b>{{ citation.filename }}</b><small>{{ citation.location }}</small></span>
            <el-empty v-if="!artifact?.citations.length" :image-size="60" description="暂无可追溯来源" />
          </el-tab-pane>
          <el-tab-pane label="警告"><div v-for="warning in artifact?.warnings || []" :key="warning" class="warning">{{ warning }}</div><el-empty v-if="!artifact?.warnings.length" :image-size="60" description="暂无警告" /></el-tab-pane>
          <el-tab-pane label="质量"><p>来源 {{ artifact?.citations.length || 0 }} 条</p><p>警告 {{ artifact?.warnings.length || 0 }} 条</p><p class="muted">详细审校请进入质量检查。</p></el-tab-pane>
          <el-tab-pane label="版本"><template v-if="artifact"><h3>当前 v{{ artifact.version_no }}</h3><p class="meta">生成、修改和回滚均创建新版本。</p></template><el-empty v-else :image-size="60" description="暂无版本" /></el-tab-pane>
        </el-tabs>
      </aside>
    </div>

    <el-drawer v-model="drawerVisible" title="资料原文" size="420px">
      <el-descriptions v-if="selectedCitation" :column="1" border><el-descriptions-item label="文件">{{ selectedCitation.filename }}</el-descriptions-item><el-descriptions-item label="位置">{{ selectedCitation.location }}</el-descriptions-item><el-descriptions-item label="分块">{{ selectedCitation.chunk_id }}</el-descriptions-item></el-descriptions>
      <blockquote v-if="selectedCitation">{{ selectedCitation.quote }}</blockquote>
    </el-drawer>
  </section>
</template>

<style scoped>
.action-error{margin-bottom:12px}.source-options{display:grid;gap:6px}.source-options .el-checkbox{max-width:100%;overflow:hidden}.skill-card small{display:block;color:#7a8599;margin:6px 0}.task-row{padding:10px 0;border-bottom:1px solid #edf0f5}.task-error{color:#d84c4c;font-size:13px;overflow-wrap:anywhere}.citation small{display:block;margin-top:4px}.artifact-area h3{margin-top:22px}blockquote{line-height:1.7;overflow-wrap:anywhere}
</style>
