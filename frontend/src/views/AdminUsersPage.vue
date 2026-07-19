<template>
  <div class="admin-users-page">
    <PageHeader title="用户与权限" description="管理账号状态和角色授权，所有变更均写入操作审计。" eyebrow="Administration">
      <template #actions><el-button :loading="loading" @click="loadUsers">刷新</el-button></template>
    </PageHeader>

    <el-alert class="permission-note" type="info" :closable="false" show-icon
      title="角色由后端定义并以数组保存；移除最后一个可用管理员会被服务端拒绝。" />

    <el-card shadow="never" class="filter-card">
      <el-form inline @submit.prevent="search">
        <el-form-item label="关键词"><el-input v-model="filters.keyword" clearable placeholder="用户名或邮箱" @keyup.enter="search" /></el-form-item>
        <el-form-item label="账号状态"><el-select v-model="filters.status" clearable placeholder="全部状态" style="width:140px"><el-option label="已启用" value="active"/><el-option label="已停用" value="inactive"/></el-select></el-form-item>
        <el-form-item><el-button type="primary" @click="search">查询</el-button><el-button @click="reset">重置</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="visibleUsers" v-loading="loading" row-key="id">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户" min-width="150">
          <template #default="{ row }"><div class="user-cell"><el-avatar :size="32">{{ row.username?.charAt(0)?.toUpperCase() }}</el-avatar><div><strong>{{ row.username }}</strong><small>{{ row.email || '未设置邮箱' }}</small></div></div></template>
        </el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '已启用' : '已停用' }}</el-tag></template></el-table-column>
        <el-table-column label="角色" min-width="280">
          <template #default="{ row }">
            <el-select v-model="roleDrafts[row.id]" multiple collapse-tags :max-collapse-tags="2" placeholder="至少选择一个角色" style="width:230px">
              <el-option v-for="role in roles" :key="role.name" :label="role.display_name" :value="role.name" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" min-width="180"><template #default="{ row }">{{ formatDate(row.last_login_at) }}</template></el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }"><el-button link type="primary" :loading="savingId===row.id" :disabled="!roleDrafts[row.id]?.length" @click="saveRoles(row)">保存角色</el-button><el-button link :type="row.is_active?'danger':'success'" :loading="statusSavingId===row.id" @click="toggleStatus(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template>
        </el-table-column>
        <template #empty><el-empty :description="errorText || '没有符合条件的用户'" /></template>
      </el-table>
      <div class="pagination"><el-pagination v-model:current-page="page.page" v-model:page-size="page.page_size" :total="page.total" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next" @change="loadUsers" /></div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import { getRoleList, getUserList, setUserRoles, setUserStatus } from '@/api/user'
import { copyRoles } from '@/utils/roles'

const users=ref([]),roles=ref([]),loading=ref(false),savingId=ref(null),statusSavingId=ref(null),errorText=ref('')
const roleDrafts=reactive({})
const filters=reactive({keyword:'',status:''})
const page=reactive({page:1,page_size:20,total:0})
const visibleUsers=computed(()=>users.value.filter((user)=>!filters.status||(filters.status==='active'?user.is_active:!user.is_active)))
const formatDate=(value)=>value?new Date(value).toLocaleString('zh-CN'):'-'

async function loadUsers(){loading.value=true;errorText.value='';try{const [userRes,roleRes]=await Promise.all([getUserList({page:page.page,page_size:page.page_size,keyword:filters.keyword||undefined}),getRoleList()]);users.value=userRes.items||[];page.total=userRes.total||0;roles.value=roleRes.roles||[];for(const user of users.value)roleDrafts[user.id]=copyRoles(user.roles)}catch{errorText.value='用户列表加载失败，请稍后重试'}finally{loading.value=false}}
function search(){page.page=1;loadUsers()}
function reset(){filters.keyword='';filters.status='';page.page=1;loadUsers()}
async function saveRoles(row){const next=[...(roleDrafts[row.id]||[])];if(!next.length)return;try{await ElMessageBox.confirm(`确认将 ${row.username} 的角色设置为：${next.join('、')}？`,'权限变更',{type:'warning'});savingId.value=row.id;await setUserRoles(row.id,next);ElMessage.success('角色已更新');await loadUsers()}catch{}finally{savingId.value=null}}
async function toggleStatus(row){const next=!row.is_active;try{await ElMessageBox.confirm(`确认${next?'启用':'停用'}用户 ${row.username}？`,'账号状态变更',{type:'warning'});statusSavingId.value=row.id;await setUserStatus(row.id,next);ElMessage.success(next?'用户已启用':'用户已停用');await loadUsers()}catch{}finally{statusSavingId.value=null}}
onMounted(loadUsers)
</script>

<style lang="scss" scoped>
.admin-users-page{max-width:$page-max-width;margin:0 auto}.permission-note,.filter-card{margin-bottom:$spacing-md}.filter-card,.table-card{border-radius:$border-radius-lg;border-color:$border-color;background:linear-gradient(180deg,rgba(255,255,255,.97),rgba(248,251,255,.9))}.filter-card :deep(.el-form-item){margin-bottom:0}.user-cell{display:flex;align-items:center;gap:10px}.user-cell strong,.user-cell small{display:block}.user-cell small{margin-top:3px;color:$text-secondary;font-size:12px}.pagination{display:flex;justify-content:flex-end;padding-top:$spacing-md}
</style>
