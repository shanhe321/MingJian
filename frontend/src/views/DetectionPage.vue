<template>
  <div class="detection-page">
    <PageHeader
      title="实时检测工作台"
      description="使用摄像头进行实时 PCB 缺陷检测，目标、帧率与推理状态同步更新。"
    >
      <template #actions>
        <el-button @click="$router.push('/history')">查看检测历史</el-button>
      </template>
    </PageHeader>

    <CameraWorkspace />
  </div>
</template>

<script setup>
import CameraWorkspace from '@/components/detect/CameraWorkspace.vue'
import PageHeader from '@/components/common/PageHeader.vue'
</script>

<style lang="scss" scoped>
.detection-page {
  width: min(1440px, 100%);
  height: 100%;
  min-width: 0;
  min-height: 0;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;

  :deep(.page-header) {
    flex: 0 0 auto;
    margin-bottom: 10px;
  }

  :deep(.page-header h1) {
    font-size: 22px;
  }

  :deep(.page-description) {
    margin-top: 5px;
    font-size: 12px;
  }

  :deep(.camera-workspace) {
    min-height: 0;
    flex: 1;
  }
}

@media (max-width: 1100px) {
  .detection-page {
    height: auto;
    min-height: 100%;
    overflow: visible;
  }
}
</style>
