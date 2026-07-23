<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type { Project, ProjectInput } from '../types'
import AppEmpty from '../components/AppEmpty.vue'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import StatusTag from '../components/StatusTag.vue'
import { useAppStore } from '../stores/app'
import { useProjectStore } from '../stores/project'
import { validateProject, workbenchPath } from '../utils/workbench'

const router = useRouter()
const app = useAppStore()
const projectStore = useProjectStore()
const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref('')
const dialog = ref(false)
const saving = ref(false)
const step = ref(0)
const form = reactive<ProjectInput>({
  name: '', subject: '语文', grade: '小学三年级', textbook_version: '',
  lesson_topic: '', lesson_count: 1, student_profile: '', teacher_requirements: '',
})
const health = computed(() => ({
  checking: ['正在检查后端服务', '检查中'], online: ['前后端连接正常', '成功'],
  offline: ['暂时无法连接后端', '失败'], timeout: ['后端响应超时', '超时'],
})[app.backend])
const healthType = computed<'success' | 'danger' | 'warning'>(() =>
  app.backend === 'online' ? 'success' : app.backend === 'offline' ? 'danger' : 'warning',
)

async function load() {
  loading.value = true
  error.value = ''
  try { projects.value = await api.projects() }
  catch (requestError) { error.value = (requestError as Error).message }
  finally { loading.value = false }
}

function openProject(project: Project) {
  projectStore.select(project.id)
  router.push(workbenchPath(project.id))
}

function fillDemo() {
  Object.assign(form, {
    name: '水的三态变化演示课', subject: '科学', grade: '小学三年级', textbook_version: '自编公开样例',
    lesson_topic: '水的三态变化', lesson_count: 1, student_profile: '',
    teacher_requirements: '单课时40分钟，突出观察、描述和安全提示。',
  })
  step.value = 0
  dialog.value = true
}

function next() {
  const message = validateProject(form)
  if (message) return ElMessage.warning(message)
  step.value++
}

async function create() {
  const message = validateProject(form)
  if (message) return ElMessage.warning(message)
  saving.value = true
  try {
    const project = await api.createProject(form)
    projectStore.select(project.id)
    dialog.value = false
    await router.push(workbenchPath(project.id))
  } catch (requestError) {
    ElMessage.error((requestError as Error).message)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h2>备课项目</h2>
        <p>从课程信息开始，AI 会把资料、设计、课件与评价组织成同一条教学链。</p>
      </div>
      <div class="row">
        <el-button @click="fillDemo">填入演示课题</el-button>
        <el-button type="primary" size="large" @click="dialog = true">＋ 开始备课</el-button>
      </div>
    </div>

    <div :class="['panel', 'panel-pad', 'health-strip', app.backend]">
      <div>
        <p class="eyebrow">系统连通性</p>
        <h3>{{ health[0] }} <el-tag :type="healthType">{{ health[1] }}</el-tag></h3>
        <p class="muted">{{ app.healthError || (app.backend === 'checking' ? '正在请求 /health' : '/health 已成功返回') }}</p>
      </div>
      <el-button :loading="app.backend === 'checking'" @click="app.checkHealth">重新检查</el-button>
    </div>

    <AppLoading v-if="loading" />
    <AppError v-else-if="error" :error="error" @retry="load" />
    <AppEmpty v-else-if="!projects.length" text="还没有备课项目，创建第一个课例吧" />
    <div v-else class="project-grid">
      <article v-for="project in projects" :key="project.id" class="panel project-card" tabindex="0"
        @click="openProject(project)" @keyup.enter="openProject(project)">
        <div class="card-head">
          <el-tag effect="plain">{{ project.grade }} · {{ project.subject }}</el-tag>
          <StatusTag :status="project.status" />
        </div>
        <h3>{{ project.name }}</h3>
        <p>{{ project.lesson_topic }}</p>
        <div class="meta">{{ project.textbook_version || '未指定教材版本' }} · {{ project.lesson_count }} 课时</div>
        <div class="meta">更新于 {{ new Date(project.updated_at).toLocaleString() }}</div>
      </article>
    </div>

    <el-dialog v-model="dialog" title="创建备课项目" width="720" @closed="step = 0">
      <el-steps :active="step" finish-status="success" class="steps">
        <el-step title="基础信息" /><el-step title="学情与要求" /><el-step title="确认创建" />
      </el-steps>
      <el-form label-position="top">
        <template v-if="step === 0">
          <div class="row">
            <el-form-item class="grow" label="项目名称" required><el-input v-model="form.name" maxlength="120" /></el-form-item>
            <el-form-item class="grow" label="课题" required><el-input v-model="form.lesson_topic" maxlength="160" /></el-form-item>
          </div>
          <div class="row">
            <el-form-item class="grow" label="学科" required>
              <el-select v-model="form.subject" style="width:100%"><el-option v-for="item in ['语文','数学','英语','科学','道德与法治']" :key="item" :value="item" /></el-select>
            </el-form-item>
            <el-form-item class="grow" label="年级" required><el-input v-model="form.grade" maxlength="40" /></el-form-item>
            <el-form-item label="课时"><el-input-number v-model="form.lesson_count" :min="1" :max="8" /></el-form-item>
          </div>
          <el-form-item label="教材版本"><el-input v-model="form.textbook_version" maxlength="80" /></el-form-item>
        </template>
        <template v-else-if="step === 1">
          <el-form-item label="班级特点 / 薄弱点（可选）"><el-input v-model="form.student_profile" type="textarea" :rows="4" maxlength="2000" show-word-limit /></el-form-item>
          <el-form-item label="教师补充要求（可选）"><el-input v-model="form.teacher_requirements" type="textarea" :rows="4" maxlength="3000" show-word-limit /></el-form-item>
          <el-alert title="资料按项目隔离。创建后可在工作台选择本项目中已就绪的资料。" type="info" :closable="false" />
        </template>
        <el-descriptions v-else :column="2" border>
          <el-descriptions-item label="项目">{{ form.name }}</el-descriptions-item>
          <el-descriptions-item label="课题">{{ form.lesson_topic }}</el-descriptions-item>
          <el-descriptions-item label="课程">{{ form.grade }} · {{ form.subject }}</el-descriptions-item>
          <el-descriptions-item label="教材">{{ form.textbook_version || '未指定' }}</el-descriptions-item>
          <el-descriptions-item label="学情" :span="2">{{ form.student_profile || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="补充要求" :span="2">{{ form.teacher_requirements || '未填写' }}</el-descriptions-item>
        </el-descriptions>
      </el-form>
      <template #footer>
        <el-button v-if="step" @click="step--">上一步</el-button>
        <el-button v-if="step < 2" type="primary" @click="next">下一步</el-button>
        <el-button v-else type="primary" :loading="saving" :disabled="saving" @click="create">创建并进入工作台</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.health-strip,.card-head{display:flex;align-items:center;justify-content:space-between}.health-strip{margin-bottom:20px;border-left:4px solid #f4b55e}.health-strip.online{border-left-color:#55d9a4}.health-strip.offline{border-left-color:#ff7c78}.health-strip h3{margin:6px 0}.health-strip p:last-child{margin:0}.project-card .meta{margin-top:8px}.steps{margin-bottom:24px}
</style>
