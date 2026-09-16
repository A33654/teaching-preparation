<template>
  <div class="auth-wrap">
    <el-card class="auth-card">
      <div class="auth-head">
        <div class="auth-logo">🔒</div>
        <h2>重置密码</h2>
        <p>请设置您的新密码</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="form.new_password"
            type="password"
            placeholder="至少 8 位密码"
            size="large"
            show-password
            :prefix-icon="Lock"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input
            v-model="form.confirm"
            type="password"
            placeholder="再次输入新密码"
            size="large"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="submit">
          重置密码
        </el-button>
      </el-form>

      <div class="auth-links">
        <router-link to="/login">返回登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage, type FormInstance, type FormRules } from "element-plus"
import { Lock } from "@element-plus/icons-vue"
import { authApi } from "@/api"

const route = useRoute()
const router = useRouter()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ new_password: "", confirm: "" })

const rules: FormRules = {
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" },
  ],
  confirm: [
    {
      validator: (_rule, value, callback) => {
        if (value !== form.new_password) callback(new Error("两次输入的密码不一致"))
        else callback()
      },
      trigger: "blur",
    },
  ],
}

async function submit() {
  await formRef.value?.validate()
  const token = String(route.query.token || "")
  if (!token) {
    ElMessage.error("重置链接无效，缺少 token")
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword({ token, new_password: form.new_password })
    ElMessage.success("密码重置成功，请重新登录")
    router.push("/login")
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || "重置失败，链接可能已过期")
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
