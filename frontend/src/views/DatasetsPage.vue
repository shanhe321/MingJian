<template>
  <div>
    <div class="page-header"><h2>数据集管理</h2><el-button type="primary" @click="openEditor()">新建数据集</el-button></div>
    <el-alert title="导入 ZIP 后统一转换为 YOLO 目录；数据集必须同时包含训练集和验证集才能用于训练。" type="info" show-icon :closable="false" style="margin-bottom:12px" />
    <el-table :data="items" v-loading="loading">
      <el-table-column prop="name" label="名称" />
      <el-table-column label="场景" min-width="150"><template #default="{ row }">{{ sceneName(row.scene_id) }}</template></el-table-column>
      <el-table-column prop="status" label="状态"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
      <el-table-column prop="total_images" label="总图" />
      <el-table-column prop="train_images" label="训练" />
      <el-table-column prop="val_images" label="验证" />
      <el-table-column label="导入格式" width="130"><template #default="{ row }"><el-select v-model="formats[row.id]"><el-option v-for="f in ['yolo','voc','coco','labelme']" :key="f" :value="f" /></el-select></template></el-table-column>
      <el-table-column label="操作" min-width="260">
        <template #default="{ row }">
          <input :ref="(el) => fileInputs[row.id] = el" type="file" accept=".zip" hidden @change="(event) => doImport(row, event)" />
          <el-button link @click="showDetail(row)">详情</el-button>
          <el-button link type="primary" @click="fileInputs[row.id]?.click()">导入</el-button>
          <el-button link type="success" @click="validate(row)">校验</el-button>
          <el-button link @click="openEditor(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑数据集' : '新建数据集'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item v-if="!form.id" label="场景"><el-select v-model="form.scene_id" style="width:100%"><el-option v-for="scene in scenes" :key="scene.id" :label="scene.display_name" :value="scene.id" /></el-select></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="detailDialog" title="数据集详情" width="760px">
      <el-descriptions v-if="detail" :column="2" border style="margin-bottom: 16px">
        <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
        <el-descriptions-item label="场景">{{ sceneName(detail.scene_id) }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ statusText(detail.status) }}</el-descriptions-item>
        <el-descriptions-item label="总图片">{{ detail.total_images }}</el-descriptions-item>
        <el-descriptions-item label="训练/验证/测试">{{ detail.train_images }}/{{ detail.val_images }}/{{ detail.test_images }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ detail.updated_at }}</el-descriptions-item>
        <el-descriptions-item label="说明" :span="2">{{ detail.description || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-table v-if="detail?.images?.length" :data="detail.images" max-height="360" size="small">
        <el-table-column prop="image_name" label="图片" min-width="180" />
        <el-table-column prop="split" label="划分" width="90" />
        <el-table-column prop="width" label="宽" width="80" />
        <el-table-column prop="height" label="高" width="80" />
        <el-table-column prop="defect_count" label="标注数" width="90" />
        <el-table-column prop="status" label="状态" width="100" />
      </el-table>
      <el-empty v-else description="尚未导入图片" />
    </el-dialog>
  </div>
</template>

<script setup>
import { createDataset, deleteDataset, getDataset, getDatasets, importDataset, updateDataset, validateDataset } from '@/api/datasets'
import { getScenes } from '@/api/scenes'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

const items=ref([]), scenes=ref([]), loading=ref(false), dialog=ref(false), detailDialog=ref(false), detail=ref(null); const formats=reactive({}), fileInputs=reactive({})
const form=reactive({ id:null, name:'', scene_id:null, description:'' })
const statusMap={prepared:'待导入',validating:'校验中',ready:'可训练',failed:'失败'}
function statusText(status){return statusMap[status]||status}
function statusType(status){return status==='ready'?'success':status==='failed'?'danger':status==='validating'?'warning':'info'}
function sceneName(sceneId){return scenes.value.find((scene)=>scene.id===sceneId)?.display_name||`场景 #${sceneId}`}
async function load(){loading.value=true;try{const [d,s]=await Promise.all([getDatasets(),getScenes()]);items.value=d.items||[];scenes.value=s.items||[];items.value.forEach((row)=>{formats[row.id] ||= 'yolo'})}finally{loading.value=false}}
function openEditor(row){Object.assign(form,row?{id:row.id,name:row.name,scene_id:row.scene_id,description:row.description||''}:{id:null,name:'',scene_id:scenes.value[0]?.id||null,description:''});dialog.value=true}
async function showDetail(row){try{detail.value=await getDataset(row.id);detailDialog.value=true}catch{}}
async function save(){
  const name=form.name.trim()
  if(!name){ElMessage.warning('请输入数据集名称');return}
  if(!form.id&&!form.scene_id){ElMessage.warning('请选择检测场景');return}
  try{
    if(form.id)await updateDataset(form.id,{name,description:form.description})
    else await createDataset({name,scene_id:form.scene_id,description:form.description})
    ElMessage.success('数据集已保存');dialog.value=false;await load()
  }catch{
    // HTTP 错误已由 request 拦截器提示；在组件内接住，避免被全局
    // unhandledrejection 误报成“页面渲染出错”。
  }
}
async function doImport(row,event){const file=event.target.files?.[0];if(!file)return;loading.value=true;try{await importDataset(row.id,file,formats[row.id]);ElMessage.success('导入完成，请继续校验');await load()}catch{}finally{event.target.value='';loading.value=false}}
async function validate(row){try{const result=await validateDataset(row.id);result.valid?ElMessage.success('数据集校验通过'):ElMessage.error(result.errors?.join('；')||'校验失败');await load()}catch{}}
async function remove(row){try{await ElMessageBox.confirm(`删除数据集 ${row.name}？`,'确认',{type:'warning'});await deleteDataset(row.id);ElMessage.success('已删除');await load()}catch{}}
onMounted(load)
</script>
<style scoped>.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.page-header h2{margin:0}</style>
