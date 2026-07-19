<template><div class="metric-grid"><article v-for="item in metrics" :key="item.label"><span>{{ item.label }}</span><strong>{{ format(item.value) }}</strong></article></div></template>
<script setup>
import { computed } from 'vue'
const props=defineProps({model:{type:Object,default:()=>({})}})
const metrics=computed(()=>[{label:'mAP@50',value:props.model.map50},{label:'mAP@50-95',value:props.model.map50_95},{label:'Precision',value:props.model.precision},{label:'Recall',value:props.model.recall}])
const format=(value)=>value==null?'-':`${(Number(value)*100).toFixed(2)}%`
</script>
<style lang="scss" scoped>.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric-grid article{padding:13px;border:1px solid $border-color;border-radius:$border-radius-md;background:$surface-color-soft}.metric-grid span{display:block;color:$text-secondary;font-size:12px}.metric-grid strong{display:block;margin-top:6px;color:$text-primary;font-size:18px}@media(max-width:680px){.metric-grid{grid-template-columns:repeat(2,1fr)}}</style>
