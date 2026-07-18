<template>
  <div>
    <div class="page-header"><h2>模型版本</h2><el-button @click="load">刷新</el-button></div>
    <el-table :data="items" v-loading="loading">
      <el-table-column prop="version" label="版本" />
      <el-table-column prop="model_name" label="模型" min-width="200" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="map50" label="mAP50" />
      <el-table-column prop="precision" label="Precision" />
      <el-table-column prop="recall" label="Recall" />
      <el-table-column label="默认"><template #default="{ row }"><el-tag v-if="row.is_default" type="success">默认</el-tag></template></el-table-column>
      <el-table-column label="评估产物" min-width="240"><template #default="{ row }"><el-link v-for="(url,name) in row.artifacts" :key="name" :href="url" target="_blank" style="margin-right:8px">{{ name }}</el-link></template></el-table-column>
      <el-table-column label="操作" width="230"><template #default="{ row }"><el-button link @click="showDetail(row)">详情</el-button><template v-if="userStore.isSuperuser"><el-button link type="primary" :disabled="row.is_default || row.status !== 'active'" @click="makeDefault(row)">设为默认</el-button><el-button link type="danger" :disabled="row.status !== 'active'" @click="archive(row)">归档</el-button></template></template></el-table-column>
    </el-table>
    <el-dialog v-model="detailDialog" title="模型版本详情" width="720px">
      <el-descriptions v-if="detail" :column="2" border>
        <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ detail.model_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
        <el-descriptions-item label="默认模型">{{ detail.is_default ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="mAP50">{{ metric(detail.map50) }}</el-descriptions-item>
        <el-descriptions-item label="mAP50-95">{{ metric(detail.map50_95) }}</el-descriptions-item>
        <el-descriptions-item label="Precision">{{ metric(detail.precision) }}</el-descriptions-item>
        <el-descriptions-item label="Recall">{{ metric(detail.recall) }}</el-descriptions-item>
        <el-descriptions-item label="文件大小">{{ detail.file_size || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
        <el-descriptions-item label="各类别 AP" :span="2"><pre>{{ JSON.stringify(detail.per_class_ap || {}, null, 2) }}</pre></el-descriptions-item>
        <el-descriptions-item label="缺失评估产物" :span="2">{{ detail.artifact_status?.missing?.join('、') || '无' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>
<script setup>
import { archiveModel, getModel, getModels, setDefaultModel } from '@/api/models'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
const userStore=useUserStore(),items=ref([]),loading=ref(false),detailDialog=ref(false),detail=ref(null)
async function load(){loading.value=true;try{items.value=(await getModels({include_archived:userStore.isSuperuser})).items||[]}finally{loading.value=false}}
function metric(value){return value==null?'-':Number(value).toFixed(4)}
async function showDetail(row){try{detail.value=await getModel(row.id);detailDialog.value=true}catch{}}
async function makeDefault(row){await setDefaultModel(row.id);ElMessage.success('默认模型已切换');await load()}
async function archive(row){await ElMessageBox.confirm(`归档模型 ${row.version}？`,'确认',{type:'warning'});await archiveModel(row.id);ElMessage.success('模型已归档');await load()}
onMounted(load)
</script>
<style scoped>.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.page-header h2{margin:0}</style>
