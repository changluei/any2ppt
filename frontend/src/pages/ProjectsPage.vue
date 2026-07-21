<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, type ProjectInput } from '../api'
import type { Project } from '../types'
import AppEmpty from '../components/AppEmpty.vue'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import { useAppStore } from '../stores/app'
import { useProjectStore } from '../stores/project'

const router = useRouter()
const app = useAppStore()
const projectStore = useProjectStore()
const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref('')
const dialog = ref(false)
const saving = ref(false)
const health = computed(
  () =>
    ({
      checking: ['正在检查后端服务', '检查中'],
      online: ['前后端连接正常', '成功'],
      offline: ['暂时无法连接后端', '失败'],
      timeout: ['后端响应超时', '超时'],
    })[app.backend],
)
const healthType = computed<'success' | 'danger' | 'warning'>(() =>
  app.backend === 'online' ? 'success' : app.backend === 'offline' ? 'danger' : 'warning',
)
const form = reactive<ProjectInput>({
  name: '',
  subject: '语文',
  grade: '小学三年级',
  textbook_version: '',
  lesson_topic: '',
  lesson_count: 1,
  student_profile: '',
  teacher_requirements: '',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    projects.value = await api.projects()
  } catch (requestError) {
    error.value = (requestError as Error).message
  } finally {
    loading.value = false
  }
}

function openProject(project: Project) {
  projectStore.select(project.id)
  router.push(`/workbench/${project.id}`)
}

async function create() {
  if (!form.name.trim() || !form.lesson_topic.trim()) {
    ElMessage.warning('请填写项目名称和课题')
    return
  }

  saving.value = true
  try {
    const project = await api.createProject(form)
    projectStore.select(project.id)
    dialog.value = false
    router.push(`/workbench/${project.id}`)
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
      <el-button type="primary" size="large" @click="dialog = true">＋ 开始备课</el-button>
    </div>

    <div :class="['panel', 'panel-pad', 'health-strip', app.backend]">
      <div>
        <p class="eyebrow">系统连通性</p>
        <h3>{{ health[0] }} <el-tag :type="healthType">{{ health[1] }}</el-tag></h3>
        <p class="muted">
          {{ app.healthError || (app.backend === 'checking' ? '正在请求 /health' : '/health 已成功返回') }}
        </p>
      </div>
      <el-button :loading="app.backend === 'checking'" @click="app.checkHealth">重新检查</el-button>
    </div>

    <AppLoading v-if="loading" />
    <AppError v-else-if="error" :error="error" @retry="load" />
    <AppEmpty v-else-if="!projects.length" text="还没有备课项目，创建第一个课例吧" />
    <div v-else class="project-grid">
        <article
          v-for="project in projects"
          :key="project.id"
          class="panel project-card"
          @click="openProject(project)"
        >
          <el-tag effect="plain">{{ project.grade }} · {{ project.subject }}</el-tag>
          <h3>{{ project.name }}</h3>
          <p>{{ project.lesson_topic }}</p>
          <div class="meta">
            {{ project.textbook_version || '未指定教材版本' }} · {{ project.lesson_count }} 课时
          </div>
        </article>
    </div>

    <el-dialog v-model="dialog" title="创建单课时备课项目" width="680">
      <el-form label-position="top">
        <div class="row">
          <el-form-item class="grow" label="项目名称" required>
            <el-input v-model="form.name" placeholder="例如：三年级语文公开课" />
          </el-form-item>
          <el-form-item class="grow" label="课题" required>
            <el-input v-model="form.lesson_topic" placeholder="请输入本课课题" />
          </el-form-item>
        </div>
        <div class="row">
          <el-form-item class="grow" label="学科">
            <el-select v-model="form.subject" style="width: 100%">
              <el-option
                v-for="subject in ['语文', '数学', '英语', '科学', '道德与法治']"
                :key="subject"
                :value="subject"
              />
            </el-select>
          </el-form-item>
          <el-form-item class="grow" label="年级">
            <el-input v-model="form.grade" />
          </el-form-item>
          <el-form-item class="grow" label="课时">
            <el-input-number v-model="form.lesson_count" :min="1" :max="8" />
          </el-form-item>
        </div>
        <el-form-item label="教材版本">
          <el-input v-model="form.textbook_version" placeholder="例如：人教版三年级上册" />
        </el-form-item>
        <el-form-item label="学情特点（可选）">
          <el-input v-model="form.student_profile" type="textarea" />
        </el-form-item>
        <el-form-item label="教师补充要求（可选）">
          <el-input v-model="form.teacher_requirements" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">创建并进入工作台</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.health-strip { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; border-left: 4px solid #f4b55e; }
.health-strip.online { border-left-color: #55d9a4; }
.health-strip.offline { border-left-color: #ff7c78; }
.health-strip h3 { margin: 6px 0; }
.health-strip p:last-child { margin: 0; }
</style>
