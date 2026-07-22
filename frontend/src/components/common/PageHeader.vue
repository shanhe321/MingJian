<template>
  <header class="page-header" :class="{ 'has-description': description }">
    <div class="page-title-copy">
      <h1>{{ title }}</h1>
      <p v-if="description" class="page-description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-actions"><slot name="actions" /></div>
  </header>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
})
</script>

<style lang="scss" scoped>
.page-header { display:flex; align-items:flex-start; justify-content:space-between; gap:$spacing-lg; margin-bottom:$spacing-lg; }
.page-header:not(.has-description) { align-items:center; margin-bottom:$spacing-md; }
.page-title-copy { min-width:0; }
h1 { margin:0; color:$text-primary; font-size:26px; font-weight:680; line-height:1.2; }
.page-description { margin:9px 0 0; color:$text-secondary; font-size:14px; line-height:1.6; }
.page-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:$spacing-sm; padding-top:2px; }
@media (max-width: 760px) { .page-header { flex-direction:column; align-items:flex-start; } .page-actions { width:100%; justify-content:flex-start; } }
</style>
