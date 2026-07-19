<template><section class="artifact-panel"><div class="section-heading"><h3>评估产物</h3><el-tag :type="missing.length?'warning':'success'">{{ missing.length?'部分缺失':'产物完整' }}</el-tag></div><div v-if="entries.length" class="artifact-links"><el-link v-for="([name,url]) in entries" :key="name" :href="url" target="_blank" type="primary"><el-icon><Document/></el-icon>{{ name }}</el-link></div><el-empty v-else description="暂无可用评估产物" :image-size="64"/><el-alert v-if="missing.length" type="warning" :closable="false" :title="`缺失：${missing.join('、')}`"/></section></template>
<script setup>
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'
const props=defineProps({artifacts:{type:Object,default:()=>({})},artifactStatus:{type:Object,default:()=>({})}})
const entries=computed(()=>Object.entries(props.artifacts||{}));const missing=computed(()=>props.artifactStatus?.missing||[])
</script>
<style lang="scss" scoped>.artifact-panel{margin-top:$spacing-lg}.section-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.section-heading h3{margin:0;color:$text-primary;font-size:15px}.artifact-links{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}.artifact-links :deep(.el-link){padding:9px 12px;border:1px solid $border-color;border-radius:$border-radius-md;background:$surface-color-soft}.artifact-links .el-icon{margin-right:6px}</style>
