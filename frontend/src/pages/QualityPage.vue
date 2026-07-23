<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import type { ApiError, GraphState, QualityIssue } from '../types'
import AppError from '../components/AppError.vue'
import AppLoading from '../components/AppLoading.vue'
import StatusTag from '../components/StatusTag.vue'
import { canExport, elapsedText, issueTargetRoute } from '../utils/workbench'

const router = useRouter()
const projectId = String(useRoute().params.projectId)
const graph = ref<GraphState>({ status: 'not_started', nodes: [], issues: [] })
const loading = ref(true)
const error = ref<ApiError>()
const busy = ref(false)
let timer: number | undefined
const labels: Record<string, string> = {
  analyze_sources: '资料分析', design_lesson: '教学设计', generate_slides: '课件生成',
  generate_notes_exercises: '讲稿/练习', review_quality: '质量审校', human_confirm: '人工确认', finalize: '导出准备',
}
const current = computed(() => graph.value.nodes.find(({ node_id }) => node_id === graph.value.current_node))

function schedule() {
  clearTimeout(timer)
  if (graph.value.status === 'running') timer = window.setTimeout(load, 1500)
}

async function load() {
  error.value = undefined
  try { graph.value = await api.graph(projectId) }
  catch (requestError) { error.value = requestError as ApiError }
  finally { loading.value = false; if (!error.value) schedule() }
}

async function decide(decision: 'accept' | 'revise' | 'cancel') {
  if (!graph.value.id || busy.value) return
  busy.value = true
  try {
    await api.confirmGraph(graph.value.id, decision)
    ElMessage.success('已提交教师决定')
    await load()
  } catch (requestError) { error.value = requestError as ApiError }
  finally { busy.value = false }
}

async function resume() {
  if (!graph.value.id || busy.value) return
  busy.value = true
  try { graph.value = await api.resumeGraph(graph.value.id); schedule() }
  catch (requestError) { error.value = requestError as ApiError }
  finally { busy.value = false }
}

async function cancelRun() {
  if (!graph.value.id || busy.value) return
  busy.value = true
  try {
    graph.value = await api.cancelGraph(graph.value.id)
    ElMessage.success('流程已取消，可稍后从检查点恢复')
  } catch (requestError) { error.value = requestError as ApiError }
  finally { busy.value = false }
}

function locate(issue: QualityIssue) {
  router.push(issueTargetRoute(projectId, issue.target_id))
}

async function copyThread() {
  if (!graph.value.thread_id) return
  try { await navigator.clipboard.writeText(graph.value.thread_id); ElMessage.success('thread_id 已复制') }
  catch { ElMessage.error('复制失败，请手动记录 thread_id') }
}

onMounted(load)
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <section>
    <div class="page-head">
      <div><h2>多智能体质量流程</h2><p>生成、定向返修与教师确认均来自后端真实状态。</p></div>
      <el-button @click="router.push(`/workbench/${projectId}`)">返回工作台</el-button>
    </div>
    <AppLoading v-if="loading" />
    <AppError v-else-if="error && !graph.id" :error="error.message" @retry="load" />
    <div v-else class="panel panel-pad">
      <el-alert v-if="error" type="error" :closable="false" :title="error.message"><template #default><el-button link type="danger" @click="load">重试</el-button></template></el-alert>
      <div class="flow-head"><div><h3>流程状态 <StatusTag :status="graph.status" /></h3><p class="meta">总尝试 {{ graph.attempt || 0 }} 次 · 已用 {{ elapsedText(graph.created_at, graph.updated_at) }}</p></div><div><el-button v-if="graph.status === 'running'" text type="warning" :loading="busy" @click="cancelRun">取消流程</el-button><el-button v-if="graph.thread_id" text @click="copyThread">复制 thread_id</el-button></div></div>
      <div v-if="graph.nodes.length" class="node-flow">
        <template v-for="(node,index) in graph.nodes" :key="node.node_id"><button :class="['node',node.status,{current:node.node_id === graph.current_node}]" type="button"><b>{{ labels[node.node_id] || node.node_id }}</b><small><StatusTag :status="node.status" /> · 尝试 {{ node.attempt }}</small></button><span v-if="index < graph.nodes.length - 1">→</span></template>
      </div>
      <el-empty v-else description="尚未运行完整生成任务" />

      <el-alert v-if="current" class="section-gap" :closable="false" :title="`当前节点：${labels[current.node_id] || current.node_id}；已尝试 ${current.attempt} 次`" type="info" />
      <el-alert v-if="graph.state_snapshot?.recovery_message || graph.state_snapshot?.error" class="section-gap" :closable="false" type="warning" :title="graph.state_snapshot.recovery_message || graph.state_snapshot.error" />
      <el-alert v-if="graph.status === 'needs_revision'" class="section-gap" :closable="false" type="warning" :title="`仅返修：${graph.state_snapshot?.repair_scope || '问题对应内容'}，已通过部分不会全部重做。`" />
      <el-alert v-if="(graph.attempt || 0) > 2" class="section-gap" :closable="false" type="error" title="自动尝试次数较多，请转为人工处理。" />

      <el-divider /><h3>审校问题</h3>
      <p v-if="!graph.issues.length" class="muted">确定性规则未发现阻断问题，最终内容仍需教师确认。</p>
      <button v-for="issue in graph.issues" :key="issue.target_id + issue.issue_type" :class="['issue',issue.severity]" type="button" @click="locate(issue)">
        <b>{{ issue.target_id }} · {{ issue.issue_type }}</b><p>{{ issue.suggestion }}</p><small>点击定位到对应内容 →</small>
      </button>

      <template v-if="['awaiting_confirmation','needs_revision'].includes(graph.status)">
        <el-divider /><h3>教师人工确认</h3><p>AI 仅提供备课草案，确认权始终属于教师。</p>
        <el-button :disabled="busy" @click="decide('cancel')">取消流程</el-button><el-button :disabled="busy" @click="decide('revise')">返回修改</el-button><el-button type="primary" :loading="busy" @click="decide('accept')">接受并允许导出</el-button>
      </template>
      <el-button v-if="['failed','cancelled','needs_revision'].includes(graph.status)" type="warning" :loading="busy" @click="resume">继续处理</el-button>
      <el-result v-if="canExport(graph.status)" icon="success" title="教师已确认" sub-title="现在可以选择版本并导出教师包或学生包"><template #extra><el-button type="primary" @click="router.push(`/export/${projectId}`)">前往导出</el-button></template></el-result>
    </div>
  </section>
</template>

<style scoped>
.flow-head,.node{display:flex;justify-content:space-between;align-items:center}.node{border:0;gap:8px;cursor:pointer}.node small{display:flex;align-items:center;gap:4px}.node.current{outline:2px solid #4c88e8}.issue{display:block;width:100%;text-align:left;border:0;cursor:pointer}.issue p{overflow-wrap:anywhere}.section-gap{margin:14px 0}
</style>
