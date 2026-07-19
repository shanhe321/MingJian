<template>
  <section v-if="result" class="validation-result" :class="result.valid?'is-valid':'is-invalid'">
    <div class="result-title"><el-icon><CircleCheckFilled v-if="result.valid"/><CircleCloseFilled v-else/></el-icon><strong>{{ result.valid ? '数据集校验通过' : '数据集校验未通过' }}</strong></div>
    <p>当前状态：{{ statusLabel('dataset',result.status) }}</p>
    <ul v-if="result.errors?.length"><li v-for="(error,index) in result.errors" :key="index">{{ error }}</li></ul>
  </section>
</template>
<script setup>
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { statusLabel } from '@/utils/statusMaps'
defineProps({result:{type:Object,default:null}})
</script>
<style lang="scss" scoped>.validation-result{margin:0 0 $spacing-md;padding:14px 16px;border:1px solid rgba(22,163,104,.25);border-radius:$border-radius-lg;background:rgba(22,163,104,.06)}.validation-result.is-invalid{border-color:rgba(220,90,90,.28);background:rgba(220,90,90,.06)}.result-title{display:flex;align-items:center;gap:8px;color:$text-primary}.validation-result p{margin:6px 0 0;color:$text-secondary;font-size:13px}.validation-result ul{margin:10px 0 0;padding-left:20px;color:$danger-color;font-size:13px;line-height:1.7}</style>
