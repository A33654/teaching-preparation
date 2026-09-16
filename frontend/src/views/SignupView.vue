<template>
  <div class="auth-wrap">
    <el-card class="auth-card">
      <div class="auth-head">
        <div class="auth-logo">📚</div>
        <h2>注册账号</h2>
        <p>加入 AI 教学助手，开启智能备课</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" size="large" :prefix-icon="Message" />
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <el-input v-model="form.full_name" placeholder="请输入姓名（可选）" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少 8 位密码"
            size="large"
            show-password
            :prefix-icon="Lock"
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input
            v-model="form.confirm"
            type="password"
            placeholder="再次输入密码"
            size="large"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="submit">
          注 册
        </el-button>
      </el-form>

      <div class="auth-links">
        <router-link to="/login">已有账号？去登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, type FormInstance, type FormRules } from "element-plus"
import { Message, Lock, User } from "@element-plus/icons-vue"
import { useAuthStore } from "@/stores/auth"

const router = useRouter()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ email: "", full_name: "", password: "", confirm: "" })

const rules: FormRules = {
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" },
  ],
  confirm: [
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error("两次输入的密码不一致"))
        else callback()
      },
      trigger: "blur",
    },
  ],
}

async function submit() {
  await formRef.value?.validate()
  loading.value = true
  try {
    await auth.register({ email: form.email, password: form.password, full_name: form.full_name })
    ElMessage.success("注册成功，请登录")
    router.push("/login")
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || "注册失败")
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
