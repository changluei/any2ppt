<script setup lang="ts">
/** 列表为空时的统一占位组件。 */
defineProps<{ text?: string }>()
</script>

<template>
  <div class="empty-wrap"><el-empty :description="text || '暂无内容'" /></div>
</template>
