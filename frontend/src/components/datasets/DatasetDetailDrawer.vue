<template>
  <el-drawer :model-value="modelValue" title="数据集详情" size="min(760px, 92vw)" @update:model-value="$emit('update:modelValue',$event)">
    <AsyncState v-if="loading" state="loading" compact />
    <AsyncState v-else-if="error" state="error" :message="error" compact @retry="$emit('retry')" />
    <div v-else>
      <DatasetValidationResult :result="validationResult"/>
      <el-descriptions v-if="dataset" :column="2" border>
        <el-descriptions-item label="名称">{{ dataset.name }}</el-descriptions-item><el-descriptions-item label="场景">{{ sceneName }}</el-descriptions-item>
        <el-descriptions-item label="状态"><StatusTag group="dataset" :status="dataset.status"/></el-descriptions-item><el-descriptions-item label="所有者">用户 #{{ dataset.user_id }}</el-descriptions-item>
        <el-descriptions-item label="图片">{{ dataset.total_images||0 }}</el-descriptions-item><el-descriptions-item label="训练 / 验证 / 测试">{{ dataset.train_images||0 }} / {{ dataset.val_images||0 }} / {{ dataset.test_images||0 }}</el-descriptions-item>
        <el-descriptions-item label="标注数量">{{ annotationCount }}</el-descriptions-item><el-descriptions-item label="更新时间">{{ formatDate(dataset.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="说明" :span="2">{{ dataset.description||'-' }}</el-descriptions-item>
      </el-descriptions>
      <div class="drawer-heading"><h3>图片与标注质量</h3><span>{{ dataset?.images?.length||0 }} 项</span></div>
      <el-table v-if="dataset?.images?.length" :data="dataset.images" size="small" max-height="460">
        <el-table-column prop="image_name" label="图片" min-width="200" show-overflow-tooltip/><el-table-column prop="split" label="划分" width="80"/><el-table-column label="尺寸" width="110"><template #default="{row}">{{ row.width||'-' }} × {{ row.height||'-' }}</template></el-table-column><el-table-column prop="defect_count" label="标注" width="80"/><el-table-column prop="status" label="质量" width="100"><template #default="{row}"><el-tag :type="row.status==='valid'?'success':row.status==='invalid'?'danger':'info'">{{ {valid:'有效',invalid:'无效',ignored:'已忽略'}[row.status]||row.status }}</el-tag></template></el-table-column>
      </el-table><el-empty v-else-if="dataset" description="尚未导入图片"/>
    </div>
  </el-drawer>
</template>
<script setup>
import { computed } from 'vue'
import DatasetValidationResult from './DatasetValidationResult.vue'
import AsyncState from '@/components/common/AsyncState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
const props=defineProps({modelValue:Boolean,dataset:{type:Object,default:null},scenes:{type:Array,default:()=>[]},loading:Boolean,error:{type:String,default:''},validationResult:{type:Object,default:null}})
defineEmits(['update:modelValue','retry'])
const sceneName=computed(()=>props.scenes.find((item)=>item.id===props.dataset?.scene_id)?.display_name||`场景 #${props.dataset?.scene_id??'-'}`)
const annotationCount=computed(()=>(props.dataset?.images||[]).reduce((sum,item)=>sum+(item.defect_count||0),0))
const formatDate=(value)=>value?new Date(value).toLocaleString('zh-CN'):'-'
</script>
<style lang="scss" scoped>.drawer-heading{display:flex;align-items:center;justify-content:space-between;margin:22px 0 10px}.drawer-heading h3{margin:0;color:$text-primary;font-size:15px}.drawer-heading span{color:$text-secondary;font-size:12px}</style>
