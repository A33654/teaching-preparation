<template>
  <div>
    <div class="page-header">
      <div>
        <h1>管理后台</h1>
        <div class="subtitle">用户管理（仅超级管理员可见）</div>
      </div>
    </div>

    <div class="card-panel">
      <el-table v-loading="loading" :data="users" stripe>
        <el-table-column label="用户" min-width="200">
          <template #default="{ row }">
            <b>{{ row.full_name || row.nickname || "未设置姓名" }}</b>
            <div class="muted">{{ row.email }}</div>
          </template>
        </el-table-column>
        <el-table-column label="任教学科" width="110">
          <template #default="{ row }">{{ row.subject || "—" }}</template>
        </el-table-column>
        <el-table-column label="学段" width="90">
          <template #default="{ row }">{{ row.grade_level || "—" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? "正常" : "禁用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.is_superuser" size="small" type="warning">超级管理员</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">普通用户</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="toggleActive(row)">
              {{ row.is_active ? "禁用" : "启用" }}
            </el-button>
            <el-button size="small" type="warning" plain @click="toggleSuperuser(row)">
              {{ row.is_superuser ? "取消管理员" : "设为管理员" }}
            </el-button>
            <el-popconfirm title="确定删除该用户？" @confirm="removeUser(row)">
              <template #reference>
                <el-button size="small" type="danger" plain :icon="Delete" />
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { Delete } from "@element-plus/icons-vue"
import { adminApi } from "@/api"
import { useAuthStore } from "@/stores/auth"
import type { UserPublic } from "@/types"

const auth = useAuthStore()
const users = ref<UserPublic[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const resp = await adminApi.users({ limit: 200 })
    users.value = resp.data.data
  } finally {
    loading.value = false
  }
}

async function toggleActive(row: UserPublic) {
  if (row.id === auth.user?.id) {
    ElMessage.warning("不能操作自己的账号")
    return
  }
  await adminApi.updateUser(row.id, { is_active: !row.is_active })
  ElMessage.success("已更新")
  load()
}

async function toggleSuperuser(row: UserPublic) {
  if (row.id === auth.user?.id) {
    ElMessage.warning("不能修改自己的角色")
    return
  }
  await adminApi.updateUser(row.id, { is_superuser: !row.is_superuser })
  ElMessage.success("已更新")
  load()
}

async function removeUser(row: UserPublic) {
  if (row.id === auth.user?.id) {
    ElMessage.warning("不能删除自己的账号")
    return
  }
  await adminApi.deleteUser(row.id)
  ElMessage.success("已删除")
  load()
}

function formatTime(t?: string | null): string {
  if (!t) return "—"
  return new Date(t).toLocaleString("zh-CN", { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.muted {
  color: #909399;
  font-size: 12px;
}
</style>
