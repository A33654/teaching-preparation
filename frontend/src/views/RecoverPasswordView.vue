<template>
  <div class="auth-wrap">
    <el-card class="auth-card">
      <div class="auth-head">
        <div class="auth-logo">📧</div>
        <h2>找回密码</h2>
        <p>输入注册邮箱，我们将发送密码重置链接</p>
      </div>

      <el-form @submit.prevent>
        <el-form-item label="邮箱">
          <el-input v-model="email" placeholder="请输入注册邮箱" size="large" :prefix-icon="Message" />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="submit">
          发送重置邮件
        </el-button>
      </el-form>

      <div class="auth-links">
        <router-link to="/login">返回登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { Message } from "@element-plus/icons-vue"
import { authApi } from "@/api"

const email = ref("")
const loading = ref(false)

async function submit() {
  if (!email.value) {
    ElMessage.warning("请输入邮箱")
    return
  }
  loading.value = true
  try {
    await authApi.recoverPassword(email.value)
    ElMessage.success("重置邮件已发送，请查收（如未收到请检查垃圾箱）")
  } catch {
    // 拦截器已提示错误
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fdf2f8 0%, #f5f3ff 50%, #eff6ff 100%);
  padding: 20px;
}

.auth-card {
  width: 400px;
  border-radius: 12px;
}

.auth-head {
  text-align: center;
  margin-bottom: 24px;
}

.auth-logo {
  font-size: 40px;
}

.auth-head h2 {
  margin: 8px 0 4px;
  font-size: 22px;
}

.auth-head p {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
}

.auth-links {
  display: flex;
  justify-content: center;
  margin-top: 16px;
  font-size: 13px;
}

.auth-links a {
  color: #ec4899;
  text-decoration: none;
}
</style>
