<template>
  <div class="settings-wrap">
    <div class="page-header">
      <div>
        <h1>个人设置</h1>
        <div class="subtitle">完善教师信息，AI 助手将据此个性化回答</div>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header><b>基本资料</b></template>
          <el-form :model="form" label-width="90px">
            <el-form-item label="姓名">
              <el-input v-model="form.full_name" placeholder="真实姓名" />
            </el-form-item>
            <el-form-item label="昵称">
              <el-input v-model="form.nickname" placeholder="显示昵称" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="form.email" disabled />
              <div class="form-hint">邮箱为登录账号，暂不支持修改</div>
            </el-form-item>
            <el-form-item label="学科">
              <el-input v-model="form.subject" placeholder="如：数学（AI 助手将据此推荐内容）" />
            </el-form-item>
            <el-form-item label="学段">
              <el-select v-model="form.grade_level" clearable placeholder="选择任教学段">
                <el-option label="小学" value="小学" />
                <el-option label="初中" value="初中" />
                <el-option label="高中" value="高中" />
              </el-select>
            </el-form-item>
            <el-form-item label="学校">
              <el-input v-model="form.school" placeholder="所在学校" />
            </el-form-item>
            <el-form-item label="电话">
              <el-input v-model="form.phone" placeholder="联系电话" />
            </el-form-item>
            <el-form-item label="个人简介">
              <el-input v-model="form.bio" type="textarea" :rows="3" placeholder="一句话介绍自己" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveProfile">保存资料</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never">
          <template #header><b>修改密码</b></template>
          <el-form ref="pwdRef" :model="pwd" :rules="pwdRules" label-width="90px">
            <el-form-item label="当前密码" prop="current_password">
              <el-input v-model="pwd.current_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwd.new_password" type="password" show-password placeholder="至少 8 位" />
            </el-form-item>
            <el-form-item label="确认新密码" prop="confirm">
              <el-input v-model="pwd.confirm" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="changingPwd" @click="changePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="about-card">
          <template #header><b>技术栈</b></template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="Agent 框架">LangGraph</el-descriptions-item>
            <el-descriptions-item label="知识图谱">Neo4j</el-descriptions-item>
            <el-descriptions-item label="后端">FastAPI</el-descriptions-item>
            <el-descriptions-item label="前端">Vue 3 + Element Plus</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { ElMessage, type FormInstance, type FormRules } from "element-plus"
import { authApi } from "@/api"
import { useAuthStore } from "@/stores/auth"

const auth = useAuthStore()

const form = reactive({
  full_name: "",
  nickname: "",
  email: "",
  subject: "",
  grade_level: null as string | null,
  school: "",
  phone: "",
  bio: "",
})
const saving = ref(false)

const pwdRef = ref<FormInstance>()
const pwd = reactive({ current_password: "", new_password: "", confirm: "" })
const changingPwd = ref(false)

const pwdRules: FormRules = {
  current_password: [{ required: true, message: "请输入当前密码", trigger: "blur" }],
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" },
  ],
  confirm: [
    {
      validator: (_r, v, cb) => {
        if (v !== pwd.new_password) cb(new Error("两次输入的密码不一致"))
        else cb()
      },
      trigger: "blur",
    },
  ],
}

onMounted(() => {
  const u = auth.user
  if (u) {
    form.full_name = u.full_name || ""
    form.nickname = u.nickname || ""
    form.email = u.email
    form.subject = u.subject || ""
    form.grade_level = u.grade_level || null
    form.school = u.school || ""
    form.phone = u.phone || ""
    form.bio = u.bio || ""
  }
})

async function saveProfile() {
  saving.value = true
  try {
    await authApi.updateMe({
      full_name: form.full_name,
      nickname: form.nickname,
      subject: form.subject,
      grade_level: form.grade_level,
      school: form.school,
      phone: form.phone,
      bio: form.bio,
    })
    await auth.fetchMe()
    ElMessage.success("资料已保存")
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  await pwdRef.value?.validate()
  changingPwd.value = true
  try {
    await authApi.updatePassword({
      current_password: pwd.current_password,
      new_password: pwd.new_password,
    })
    ElMessage.success("密码已修改")
    pwd.current_password = ""
    pwd.new_password = ""
    pwd.confirm = ""
  } finally {
    changingPwd.value = false
  }
}
</script>

<style scoped>
.settings-wrap {
  max-width: 1100px;
  margin: 0 auto;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  line-height: 1.4;
}

.about-card {
  margin-top: 16px;
}
</style>
