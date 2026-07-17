<script setup lang="ts">
defineProps<{loading?:boolean;error?:string;empty?:boolean;emptyText?:string}>()
defineEmits<{retry:[]}>()
</script>
<template><div v-if="loading" class="empty-wrap"><el-skeleton :rows="4" animated/></div><div v-else-if="error" class="empty-wrap"><el-result icon="error" title="暂时无法完成请求" :sub-title="error"><template #extra><el-button type="primary" @click="$emit('retry')">重试</el-button></template></el-result></div><div v-else-if="empty" class="empty-wrap"><el-empty :description="emptyText||'暂无内容'"/></div><slot v-else/></template>
