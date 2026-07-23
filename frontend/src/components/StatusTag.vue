<script setup lang="ts">
import {computed} from 'vue'
import{statusText}from'../utils/files'
const p=defineProps<{status:string}>()
const type=computed<'success'|'danger'|'primary'|'warning'|'info'>(()=>p.status==='ready'||p.status==='succeeded'?'success':p.status==='failed'?'danger':p.status==='warn'||p.status==='needs_revision'?'warning':p.status==='running'||p.status==='parsing'||p.status==='indexing'?'primary':'info')
</script>
<template><el-tag :type="type" effect="light" round>{{statusText(status)}}</el-tag></template>
