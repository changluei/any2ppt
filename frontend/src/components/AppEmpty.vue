<script setup lang="ts">
defineProps<{ text?: string }>()
</script>

<template>
  <div class="empty-wrap"><el-empty :description="text || '暂无内容'" /></div>
</template>
