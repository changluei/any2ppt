<script setup lang="ts">
import {computed} from 'vue'
const p=defineProps<{status:string}>()
const map:Record<string,string>={uploaded:'已上传',parsing:'解析中',indexing:'索引中',ready:'已就绪',failed:'失败',pending:'等待中',running:'运行中',succeeded:'成功',cancelled:'已取消'}
const type=computed<'success'|'danger'|'primary'|'info'>(()=>p.status==='ready'||p.status==='succeeded'?'success':p.status==='failed'?'danger':p.status==='running'||p.status==='parsing'||p.status==='indexing'?'primary':'info')
</script>
<template><el-tag :type="type" effect="light" round>{{map[status]||status}}</el-tag></template>
