<template>
  <div class="audit-page">
    <PageHeader title="操作审计" description="按操作者、模块、动作和结果追踪系统关键操作。" eyebrow="Administration"><template #actions><el-button :loading="loading" @click="load">刷新</el-button></template></PageHeader>
    <el-card shadow="never" class="filter-card"><el-form inline @submit.prevent="search">
      <el-form-item label="用户 ID"><el-input-number v-model="filters.user_id" :min="1" controls-position="right" /></el-form-item>
      <el-form-item label="模块"><el-input v-model="filters.module" clearable placeholder="如 detection" /></el-form-item>
      <el-form-item label="动作"><el-input v-model="filters.action" clearable placeholder="如 delete" /></el-form-item>
      <el-form-item label="结果"><el-select v-model="filters.status" clearable placeholder="全部" style="width:120px"><el-option label="成功" value="success"/><el-option label="失败" value="failed"/></el-select></el-form-item>
      <el-form-item label="时间"><el-date-picker v-model="filters.range" type="datetimerange" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item>
      <el-form-item><el-button type="primary" @click="search">查询</el-button><el-button @click="reset">重置</el-button></el-form-item>
    </el-form></el-card>
    <el-card shadow="never" class="table-card"><el-table :data="items" v-loading="loading" row-key="id">
      <el-table-column prop="created_at" label="时间" min-width="180"><template #default="{row}">{{ formatDate(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作者" min-width="140"><template #default="{row}"><strong>{{ row.username||'-' }}</strong><small class="muted"> #{{ row.user_id??'-' }}</small></template></el-table-column>
      <el-table-column prop="module" label="模块" width="120"/><el-table-column prop="action" label="操作" width="150"/>
      <el-table-column label="目标" min-width="160"><template #default="{row}">{{ row.target_type||'-' }}<span v-if="row.target_id!=null"> #{{ row.target_id }}</span></template></el-table-column>
      <el-table-column label="结果" width="90"><template #default="{row}"><StatusTag group="audit" :status="row.status"/></template></el-table-column>
      <el-table-column prop="request_path" label="请求" min-width="200" show-overflow-tooltip/>
      <el-table-column label="操作" width="80"><template #default="{row}"><el-button link type="primary" @click="detail=row;drawer=true">详情</el-button></template></el-table-column>
      <template #empty><el-empty :description="errorText||'暂无审计记录'"/></template>
    </el-table><div class="pagination"><el-pagination v-model:current-page="page.page" v-model:page-size="page.page_size" :total="page.total" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next" @change="load"/></div></el-card>
    <el-drawer v-model="drawer" title="审计详情" size="480px"><el-descriptions v-if="detail" :column="1" border><el-descriptions-item v-for="field in detailFields" :key="field.key" :label="field.label">{{ detail[field.key]??'-' }}</el-descriptions-item></el-descriptions></el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { getAuditLogs } from '@/api/audit'
const items=ref([]),loading=ref(false),errorText=ref(''),drawer=ref(false),detail=ref(null)
const filters=reactive({user_id:undefined,module:'',action:'',status:'',range:[]})
const page=reactive({page:1,page_size:20,total:0})
const detailFields=[['id','日志 ID'],['username','用户'],['module','模块'],['action','动作'],['target_type','目标类型'],['target_id','目标 ID'],['description','说明'],['ip_address','IP'],['request_method','方法'],['request_path','路径'],['status','结果'],['error_message','错误'],['created_at','时间']].map(([key,label])=>({key,label}))
const formatDate=(value)=>value?new Date(value).toLocaleString('zh-CN'):'-'
async function load(){loading.value=true;errorText.value='';try{const res=await getAuditLogs({page:page.page,page_size:page.page_size,user_id:filters.user_id||undefined,module:filters.module||undefined,action:filters.action||undefined,status:filters.status||undefined,start_time:filters.range?.[0]||undefined,end_time:filters.range?.[1]||undefined});items.value=res.items||[];page.total=res.total||0}catch{errorText.value='审计日志加载失败，请稍后重试'}finally{loading.value=false}}
function search(){page.page=1;load()}
function reset(){Object.assign(filters,{user_id:undefined,module:'',action:'',status:'',range:[]});page.page=1;load()}
onMounted(load)
</script>

<style lang="scss" scoped>
.audit-page{max-width:$page-max-width;margin:0 auto}.filter-card{margin-bottom:$spacing-md}.filter-card,.table-card{border-radius:$border-radius-lg;border-color:$border-color;background:linear-gradient(180deg,rgba(255,255,255,.97),rgba(248,251,255,.9))}.filter-card :deep(.el-form-item){margin-bottom:8px}.pagination{display:flex;justify-content:flex-end;padding-top:$spacing-md}.muted{color:$text-secondary}
</style>
