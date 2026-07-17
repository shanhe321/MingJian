<template>
  <div class="settings-page">
    <div class="page-title-copy">
      <h2>系统设置</h2>
      <p>管理个人资料、账户安全和平台信息</p>
    </div>
    <h2>系统设置</h2>

    <el-row :gutter="24">
      <!-- 个人信息 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>个人信息</span>
          </template>

          <el-form :model="profileForm" label-width="80px">
            <el-form-item label="用户名">
              <el-input :model-value="profileForm.username" disabled />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profileForm.email" placeholder="请输入邮箱" />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="profileForm.phone" placeholder="请输入手机号" />
            </el-form-item>
            <el-form-item label="注册时间">
              <el-input :model-value="formatDate(profileForm.created_at)" disabled />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="profileLoading" @click="handleUpdateProfile">
                保存修改
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 修改密码 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>修改密码</span>
          </template>

          <el-form
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-width="100px"
          >
            <el-form-item label="当前密码" prop="old_password">
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
                placeholder="请输入当前密码"
              />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                placeholder="请输入新密码（至少 6 位）"
              />
            </el-form-item>
            <el-form-item label="确认新密码" prop="confirm_password">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                placeholder="请再次输入新密码"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="passwordLoading" @click="handleChangePassword">
                修改密码
              </el-button>
              <el-button @click="resetPasswordForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 关于系统 -->
    <el-card shadow="hover" class="about-card">
      <template #header>
        <span>关于系统</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="系统名称">RSOD Agent Platform</el-descriptions-item>
        <el-descriptions-item label="版本号">v0.1.0</el-descriptions-item>
        <el-descriptions-item label="检测模型">YOLO11n</el-descriptions-item>
        <el-descriptions-item label="前端框架">Vue 3 + Element Plus</el-descriptions-item>
        <el-descriptions-item label="后端框架">FastAPI + SQLAlchemy</el-descriptions-item>
        <el-descriptions-item label="数据库">PostgreSQL + Redis + MinIO</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
/**
 * SettingsPage.vue — 系统设置
 *
 * 功能：
 *   - 个人信息查看与修改（邮箱、手机号）
 *   - 密码修改（旧密码验证 + 新密码确认）
 *   - 系统信息展示
 */
import { getUserInfoApi } from '@/api/auth'
import { changePassword, updateProfile } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

const userStore = useUserStore()

// ── 个人信息 ──
const profileForm = reactive({
  username: '',
  email: '',
  phone: '',
  created_at: null,
})
const profileLoading = ref(false)

// ── 修改密码 ──
const passwordFormRef = ref(null)
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const passwordLoading = ref(false)

const passwordRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.new_password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

// ── 日期格式化 ──
function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

// ── 加载用户信息 ──
async function loadUserInfo() {
  try {
    const res = await getUserInfoApi()
    profileForm.username = res.username
    profileForm.email = res.email
    profileForm.phone = res.phone || ''
    profileForm.created_at = res.created_at
  } catch (err) {
    console.error('[加载用户信息失败]', err)
  }
}

// ── 更新个人信息 ──
async function handleUpdateProfile() {
  profileLoading.value = true
  try {
    await updateProfile({
      email: profileForm.email,
      phone: profileForm.phone,
    })
    ElMessage.success('个人信息已更新')
    // 同步本地用户信息，保持头部头像/用户名等展示一致
    if (userStore.user) {
      userStore.user = { ...userStore.user, email: profileForm.email, phone: profileForm.phone }
      localStorage.setItem('rsod_user', JSON.stringify(userStore.user))
    }
  } catch (err) {
    console.error('[更新个人信息失败]', err)
  } finally {
    profileLoading.value = false
  }
}

// ── 修改密码 ──
async function handleChangePassword() {
  const valid = await passwordFormRef.value.validate().catch(() => false)
  if (!valid) return

  passwordLoading.value = true
  try {
    await changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success('密码修改成功，请重新登录')
    resetPasswordForm()
  } catch (err) {
    console.error('[修改密码失败]', err)
  } finally {
    passwordLoading.value = false
  }
}

// ── 重置密码表单 ──
function resetPasswordForm() {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  passwordFormRef.value?.resetFields()
}

onMounted(() => {
  loadUserInfo()
})
</script>

<style lang="scss" scoped>
.settings-page {
  color: $text-regular;
  max-width: 920px;
  margin: 0 auto;

  > h2 {
    display: none;
  }

  .page-title-copy {
    margin-bottom: $spacing-lg;
  }

  .page-title-copy h2 {
    margin: 0 0 20px;
    color: $text-primary;
    font-size: 26px;
    font-weight: 650;
    position: relative;

    &::after {
      content: "";
      display: block;
      width: 74px;
      height: 3px;
      margin-top: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, $primary-color, $primary-color-light, #48b8f7);
    }
  }

  .page-title-copy p {
    margin: -12px 0 0;
    color: $text-secondary;
    font-size: 14px;
  }

  :deep(.el-row) {
    display: grid;
    grid-template-columns: 1fr;
    gap: $spacing-md;
    margin-left: 0 !important;
    margin-right: 0 !important;
  }

  :deep(.el-col) {
    max-width: 100%;
    padding-left: 0 !important;
    padding-right: 0 !important;
    flex: none;
  }

  :deep(.el-card) {
    border-radius: $border-radius-lg;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 251, 255, 0.88));
    border-color: $border-color;
    box-shadow:
      $shadow-sm,
      inset 0 1px 0 rgba(255, 255, 255, 0.95);
  }

  :deep(.el-card__body) {
    max-width: 680px;
  }

  :deep(.el-form-item__content) {
    max-width: 520px;
  }
}

.about-card {
  margin-top: $spacing-md;

  :deep(.el-card__body) {
    max-width: none;
  }

  :deep(.el-descriptions__body) {
    background: transparent;
  }

  :deep(.el-descriptions__table) {
    border-collapse: separate;
    border-spacing: 0 8px;
  }

  :deep(.el-descriptions__cell) {
    border: 0;
  }

  :deep(.el-descriptions__label) {
    color: $text-secondary;
    background: transparent;
  }

  :deep(.el-descriptions__content) {
    color: $text-primary;
    background: $surface-color-soft;
    border-radius: $border-radius-md;
  }
}
</style>
