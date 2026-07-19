<template>
  <el-dialog :model-value="modelValue" title="导入数据集" width="580px" :close-on-click-modal="false" @update:model-value="$emit('update:modelValue',$event)">
    <el-alert type="info" :closable="false" show-icon title="上传 ZIP 压缩包，服务端会按所选格式解析并统一转换为 YOLO 训练目录。"/>
    <el-form label-position="top" class="import-form">
      <el-form-item label="目标数据集" required><el-select v-model="form.dataset_id" style="width:100%" placeholder="选择目标数据集"><el-option v-for="item in datasets" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item>
      <el-form-item label="源标注格式" required><el-segmented v-model="form.format" :options="formatOptions" /></el-form-item>
      <el-form-item label="ZIP 文件" required>
        <el-upload drag :auto-upload="false" :limit="1" accept=".zip,application/zip" :on-change="onFile" :on-remove="()=>form.file=null"><el-icon class="el-icon--upload"><UploadFilled/></el-icon><div class="el-upload__text">拖拽 ZIP 到这里，或<em>点击选择</em></div><template #tip><div class="el-upload__tip">仅上传后端支持的 ZIP 数据集，不在前端改写文件内容。</div></template></el-upload>
      </el-form-item>
    </el-form>
    <template #footer><el-button :disabled="loading" @click="$emit('update:modelValue',false)">取消</el-button><el-button type="primary" :loading="loading" :disabled="!form.dataset_id||!form.file" @click="submit">开始导入</el-button></template>
  </el-dialog>
</template>
<script setup>
import { reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
const props=defineProps({modelValue:Boolean,datasets:{type:Array,default:()=>[]},datasetId:{type:Number,default:null},loading:Boolean})
const emit=defineEmits(['update:modelValue','submit'])
const form=reactive({dataset_id:null,format:'yolo',file:null})
const formatOptions=[{label:'YOLO',value:'yolo'},{label:'VOC',value:'voc'},{label:'COCO',value:'coco'},{label:'LabelMe',value:'labelme'}]
watch(()=>[props.modelValue,props.datasetId],()=>{if(props.modelValue){form.dataset_id=props.datasetId||props.datasets[0]?.id||null;form.format='yolo';form.file=null}},{immediate:true})
function onFile(uploadFile){form.file=uploadFile.raw}
function submit(){if(!form.file)return ElMessage.warning('请选择 ZIP 文件');emit('submit',{datasetId:form.dataset_id,format:form.format,file:form.file})}
</script>
<style lang="scss" scoped>.import-form{margin-top:$spacing-md}:deep(.el-upload){width:100%}:deep(.el-upload-dragger){width:100%;background:rgba(248,251,255,.8)}</style>
