<script setup lang="ts">
/** 可重试的统一错误态；业务页负责提供真正的 reload 回调。 */
defineProps<{ error: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="empty-wrap">
    <el-result icon="error" title="暂时无法完成请求" :sub-title="error">
      <template #extra><el-button type="primary" @click="$emit('retry')">重试</el-button></template>
    </el-result>
  </div>
</template>
