<template>
  <el-dialog :model-value="modelValue" :title="form.id ? '编辑数据集' : '新建数据集'" width="560px" :close-on-click-modal="false" @update:model-value="$emit('update:modelValue',$event)">
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="数据集名称" required><el-input v-model="form.name" maxlength="100" show-word-limit placeholder="例如：PCB 焊点缺陷数据集" /></el-form-item>
      <el-form-item v-if="!form.id" label="检测场景" required><el-select v-model="form.scene_id" style="width:100%" placeholder="选择数据集所属场景"><el-option v-for="scene in scenes" :key="scene.id" :label="scene.display_name" :value="scene.id"/></el-select></el-form-item>
      <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="记录数据来源、标注范围或训练用途"/></el-form-item>
    </el-form>
    <template #footer><el-button :disabled="loading" @click="$emit('update:modelValue',false)">取消</el-button><el-button type="primary" :loading="loading" @click="submit">保存</el-button></template>
  </el-dialog>
</template>
<script setup>
import { reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
const props=defineProps({modelValue:Boolean,dataset:{type:Object,default:null},scenes:{type:Array,default:()=>[]},loading:Boolean})
const emit=defineEmits(['update:modelValue','submit'])
const form=reactive({id:null,name:'',scene_id:null,description:''})
watch(()=>[props.modelValue,props.dataset,props.scenes],()=>{if(!props.modelValue)return;Object.assign(form,props.dataset?{id:props.dataset.id,name:props.dataset.name,scene_id:props.dataset.scene_id,description:props.dataset.description||''}:{id:null,name:'',scene_id:props.scenes[0]?.id||null,description:''})},{immediate:true})
function submit(){const name=form.name.trim();if(!name)return ElMessage.warning('请输入数据集名称');if(!form.id&&!form.scene_id)return ElMessage.warning('请选择检测场景');emit('submit',{id:form.id,name,scene_id:form.scene_id,description:form.description})}
</script>
