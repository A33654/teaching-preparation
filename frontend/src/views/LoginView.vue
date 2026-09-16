<template>
  <div class="auth-wrap">
    <el-card class="auth-card">
      <div class="auth-head">
        <div class="auth-logo">📚</div>
        <h2>AI 教学助手</h2>
        <p>基于 LangGraph + Neo4j 知识图谱的智能备课平台</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="邮箱" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入邮箱"
            size="large"
            :prefix-icon="Message"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="loading"
          @click="submit"
        >
          登 录
        </el-button>
      </el-form>

      <div class="auth-links">
        <router-link to="/recover-password">忘记密码？</router-link>
        <router-link to="/signup">注册新账号</router-link>
      </div>

      <div class="role-tip">
        <div class="tip-line">
          <el-tag size="small" type="success">教师端</el-tag>
          <span class="tip-account">teacher@example.com / teacher123456</span>
        </div>
        <div class="tip-line">
          <el-tag size="small" type="warning">管理员端</el-tag>
          <span class="tip-account">admin@example.com / admin123456</span>
        </div>
        <div class="tip-note">两个角色登录后进入不同界面</div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage, type FormInstance, type FormRules } from "element-plus"
import { Message, Lock } from "@element-plus/icons-vue"
import { useAuthStore } from "@/stores/auth"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: "", password: "" })

const rules: FormRules = {
  username: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "邮箱格式不正确", trigger: "blur" },
  ],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
}

async function submit() {
  await formRef.value?.validate()
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success("登录成功")
    const redirect = String(route.query.redirect || "")
    // 角色分流：管理员 → 管理后台；教师 → 工作台
    if (auth.user?.is_superuser) {
      router.push("/admin")
    } else if (redirect && !redirect.startsWith("/admin")) {
      router.push(redirect)
    } else {
      router.push("/")
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || "登录失败，请检查邮箱和密码")
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
  justify-content: space-between;
  margin-top: 16px;
  font-size: 13px;
}

.auth-links a {
  color: #ec4899;
  text-decoration: none;
}
</style>
