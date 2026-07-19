<template>
  <header class="page-header">
    <div class="page-title-copy">
      <p v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</p>
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
  eyebrow: { type: String, default: '' },
})
</script>

<style lang="scss" scoped>
.page-header { display:flex; align-items:flex-start; justify-content:space-between; gap:$spacing-lg; margin-bottom:$spacing-lg; }
.page-title-copy { min-width:0; }
.page-eyebrow { margin:0 0 6px; color:$primary-color; font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
h1 { margin:0; color:$text-primary; font-size:26px; font-weight:680; line-height:1.2; }
h1::after { content:""; display:block; width:74px; height:3px; margin-top:10px; border-radius:999px; background:linear-gradient(90deg,$primary-color,$primary-color-light,#48b8f7); }
.page-description { margin:9px 0 0; color:$text-secondary; font-size:14px; line-height:1.6; }
.page-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:$spacing-sm; padding-top:2px; }
@media (max-width: 760px) { .page-header { flex-direction:column; } .page-actions { width:100%; justify-content:flex-start; } }
</style>
