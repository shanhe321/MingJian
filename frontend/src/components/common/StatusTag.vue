<template><el-tag :type="meta.type" :effect="effect" :size="size"><slot>{{ meta.label }}</slot></el-tag></template>

<script setup>
import { computed } from 'vue'
import { getStatusMeta } from '@/utils/statusMaps'

const props = defineProps({
  group: { type: String, required: true },
  status: { type: [String, Number], default: '' },
  effect: { type: String, default: 'light' },
  size: { type: String, default: 'small' },
})
const meta = computed(() => getStatusMeta(props.group, props.status))
</script>
