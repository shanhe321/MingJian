<template>
  <div class="datasets-page">
    <PageHeader title="数据集" description="准备、导入并校验可用于模型训练的真实标注数据。">
      <template #actions><el-button @click="openImport()"><el-icon><Upload/></el-icon>导入数据集</el-button><el-button type="primary" @click="openEditor()"><el-icon><Plus/></el-icon>新建数据集</el-button></template>
    </PageHeader>
    <section v-if="!loadError && !listLoading" class="summary-grid"><article v-for="item in summaryCards" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.note }}</small></article></section>
    <el-card shadow="never" class="filter-card"><el-form inline @submit.prevent><el-form-item label="关键词"><el-input v-model="filters.keyword" clearable placeholder="搜索数据集名称"/></el-form-item><el-form-item label="场景"><el-select v-model="filters.scene_id" clearable placeholder="全部场景" style="width:180px"><el-option v-for="scene in scenes" :key="scene.id" :label="scene.display_name" :value="scene.id"/></el-select></el-form-item><el-form-item label="状态"><el-select v-model="filters.status" clearable placeholder="全部状态" style="width:140px"><el-option v-for="option in datasetStatuses" :key="option.value" :label="option.label" :value="option.value"/></el-select></el-form-item><el-form-item><el-button @click="resetFilters">重置</el-button><el-button :loading="listLoading" @click="load">刷新</el-button></el-form-item></el-form></el-card>
    <el-card shadow="never" class="table-card"><el-table :data="filteredItems" v-loading="listLoading" row-key="id">
      <el-table-column prop="name" label="名称" min-width="190"><template #default="{row}"><button class="name-button" type="button" @click="showDetail(row)">{{ row.name }}</button><small v-if="row.description">{{ row.description }}</small></template></el-table-column>
      <el-table-column label="场景" min-width="150"><template #default="{row}">{{ sceneName(row.scene_id) }}</template></el-table-column>
      <el-table-column v-if="userStore.isSuperuser" label="所有者" width="110"><template #default="{row}">用户 #{{ row.user_id }}</template></el-table-column>
      <el-table-column label="格式" width="100"><template #default="{row}">{{ row.total_images ? 'YOLO' : '-' }}</template></el-table-column>
      <el-table-column prop="total_images" label="图片" width="80"/><el-table-column label="标注" width="80"><template #default="{row}">{{ row.annotationCount }}</template></el-table-column>
      <el-table-column label="状态" width="110"><template #default="{row}"><StatusTag group="dataset" :status="row.status"/></template></el-table-column>
      <el-table-column label="创建时间" min-width="170"><template #default="{row}">{{ formatDate(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" min-width="270" fixed="right"><template #default="{row}"><el-button link @click="showDetail(row)">详情</el-button><el-button link type="primary" @click="openImport(row)">导入</el-button><el-button link type="success" :loading="validatingIds.has(row.id)" :disabled="row.status==='validating'" @click="validate(row)">校验</el-button><el-button link @click="openEditor(row)">编辑</el-button><el-button link type="danger" :loading="deletingId===row.id" @click="remove(row)">删除</el-button></template></el-table-column>
      <template #empty><el-empty :description="loadError||'暂无符合条件的数据集'"><el-button v-if="loadError" type="primary" @click="load">重新加载</el-button><el-button v-else type="primary" @click="openEditor()">创建第一个数据集</el-button></el-empty></template>
    </el-table></el-card>
    <DatasetEditorDialog v-model="editorVisible" :dataset="editing" :scenes="scenes" :loading="saving" @submit="save"/>
    <DatasetImportDialog v-model="importVisible" :datasets="items" :dataset-id="importTargetId" :loading="importing" @submit="runImport"/>
    <DatasetDetailDrawer v-model="detailVisible" :dataset="detail" :scenes="scenes" :loading="detailLoading" :error="detailError" :validation-result="detail?validationResults[detail.id]:null" @retry="retryDetail"/>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import DatasetEditorDialog from '@/components/datasets/DatasetEditorDialog.vue'
import DatasetImportDialog from '@/components/datasets/DatasetImportDialog.vue'
import DatasetDetailDrawer from '@/components/datasets/DatasetDetailDrawer.vue'
import { createDataset,deleteDataset,getDataset,getDatasets,importDataset,updateDataset,validateDataset } from '@/api/datasets'
import { getScenes } from '@/api/scenes'
import { useUserStore } from '@/stores/user'
import { STATUS_GROUPS } from '@/utils/statusMaps'
import { getErrorMessage } from '@/utils/errorMessages'
const userStore=useUserStore();const items=ref([]),scenes=ref([]),listLoading=ref(false),loadError=ref(''),saving=ref(false),importing=ref(false),deletingId=ref(null),editorVisible=ref(false),editing=ref(null),importVisible=ref(false),importTargetId=ref(null),detailVisible=ref(false),detailLoading=ref(false),detailError=ref(''),detailTarget=ref(null),detail=ref(null)
const validatingIds=reactive(new Set()),validationResults=reactive({}),filters=reactive({keyword:'',scene_id:'',status:''})
const datasetStatuses=Object.entries(STATUS_GROUPS.dataset).map(([value,meta])=>({value,label:meta.label}))
const filteredItems=computed(()=>items.value.filter((row)=>(!filters.keyword||row.name.toLowerCase().includes(filters.keyword.toLowerCase()))&&(!filters.scene_id||row.scene_id===filters.scene_id)&&(!filters.status||row.status===filters.status)))
const summaryCards=computed(()=>[{label:'数据集总数',value:items.value.length,note:'当前可访问项目'},{label:'Ready',value:items.value.filter(i=>i.status==='ready').length,note:'可直接用于训练'},{label:'校验中',value:items.value.filter(i=>i.status==='validating').length,note:'正在检查数据质量'},{label:'失败',value:items.value.filter(i=>i.status==='failed').length,note:'需要查看校验结果'}])
const sceneName=(id)=>scenes.value.find(s=>s.id===id)?.display_name||`场景 #${id}`;const formatDate=(v)=>v?new Date(v).toLocaleString('zh-CN'):'-'
async function load(){listLoading.value=true;loadError.value='';try{const [datasetRes,sceneRes]=await Promise.all([getDatasets(),getScenes()]);scenes.value=sceneRes.items||[];const base=datasetRes.items||[];items.value=await Promise.all(base.map(async row=>{try{const full=await getDataset(row.id);return{...row,annotationCount:(full.images||[]).reduce((n,i)=>n+(i.defect_count||0),0)}}catch{return{...row,annotationCount:'-'}}}))}catch(error){loadError.value=getErrorMessage(error);items.value=[]}finally{listLoading.value=false}}
function resetFilters(){Object.assign(filters,{keyword:'',scene_id:'',status:''})}
function openEditor(row=null){editing.value=row;editorVisible.value=true}
async function save(payload){saving.value=true;try{if(payload.id)await updateDataset(payload.id,{name:payload.name,description:payload.description});else await createDataset({name:payload.name,scene_id:payload.scene_id,description:payload.description});ElMessage.success('数据集已保存');editorVisible.value=false;await load()}catch{}finally{saving.value=false}}
function openImport(row=null){importTargetId.value=row?.id||null;importVisible.value=true}
async function runImport({datasetId,file,format}){importing.value=true;try{await importDataset(datasetId,file,format);ElMessage.success('导入完成，请继续执行数据校验');importVisible.value=false;await load()}catch{}finally{importing.value=false}}
async function validate(row){validatingIds.add(row.id);try{const result=await validateDataset(row.id);validationResults[row.id]=result;result.valid?ElMessage.success('数据集校验通过'):ElMessage.error(result.errors?.[0]||'数据集校验失败');await load();if(detail.value?.id===row.id)await showDetail(row)}catch{}finally{validatingIds.delete(row.id)}}
async function showDetail(row){detailTarget.value=row;detailVisible.value=true;detailLoading.value=true;detailError.value='';try{detail.value=await getDataset(row.id)}catch(error){detailError.value=getErrorMessage(error)}finally{detailLoading.value=false}}
function retryDetail(){if(detailTarget.value)showDetail(detailTarget.value)}
async function remove(row){try{await ElMessageBox.confirm(`确认删除数据集“${row.name}”？${userStore.isSuperuser?` 所有者为用户 #${row.user_id}。`:''} 已被训练任务引用的数据集将由后端拒绝删除。`,'删除数据集',{type:'warning',confirmButtonText:'确认删除'});deletingId.value=row.id;await deleteDataset(row.id);ElMessage.success('数据集已删除');await load()}catch{}finally{deletingId.value=null}}
onMounted(load)
</script>
<style lang="scss" scoped>
.datasets-page{max-width:$page-max-width;margin:0 auto}.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:$spacing-sm;margin-bottom:$spacing-md}.summary-grid article{padding:15px 17px;border:1px solid $border-color;border-radius:$border-radius-lg;background:#fff;box-shadow:$shadow-sm}.summary-grid span,.summary-grid small{display:block;color:$text-secondary;font-size:13px}.summary-grid strong{display:block;margin:7px 0 4px;color:$text-primary;font-size:24px}.filter-card{margin-bottom:$spacing-md}.filter-card,.table-card{border-radius:$border-radius-lg;border-color:$border-color;background:#fff}.filter-card :deep(.el-form-item){margin-bottom:0}.name-button{display:block;padding:0;border:0;background:none;color:$text-primary;font:inherit;font-weight:650;cursor:pointer}.name-button:hover{color:$primary-color}.name-button+small{display:block;max-width:240px;margin-top:4px;overflow:hidden;color:$text-secondary;font-size:13px;text-overflow:ellipsis;white-space:nowrap}@media(max-width:900px){.summary-grid{grid-template-columns:repeat(2,1fr)}}
</style>
