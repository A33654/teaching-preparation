<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-icon">📚</span>
        <span class="logo-text">AI 教学助手</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="menu"
        background-color="#1f2430"
        text-color="#a3a8b8"
        active-text-color="#ffffff"
        @select="handleMenuSelect"
      >
        <!-- 教师端菜单 -->
        <template v-if="!auth.user?.is_superuser">
          <el-menu-item index="/">
            <el-icon><HomeFilled /></el-icon>
            <span>工作台</span>
          </el-menu-item>
          <el-menu-item index="/new-lesson">
            <el-icon><Plus /></el-icon>
            <span>新建备课任务</span>
          </el-menu-item>
          <el-menu-item index="/lesson-plans">
            <el-icon><Notebook /></el-icon>
            <span>我的教案</span>
          </el-menu-item>
          <el-menu-item index="/homework">
            <el-icon><EditPen /></el-icon>
            <span>作业管理</span>
          </el-menu-item>
          <el-menu-item index="smart-grading">
            <el-icon><Checked /></el-icon>
            <span>智能批改</span>
          </el-menu-item>
          <el-menu-item index="/documents">
            <el-icon><Folder /></el-icon>
            <span>我的素材库</span>
          </el-menu-item>
          <el-menu-item index="/ppt">
            <el-icon><Film /></el-icon>
            <span>PPT 生成</span>
          </el-menu-item>
          <el-menu-item index="/my-suggestions">
            <el-icon><Promotion /></el-icon>
            <span>我的共建</span>
          </el-menu-item>
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>个人设置</span>
          </el-menu-item>
        </template>
        <!-- 管理员端菜单 -->
        <template v-if="auth.user?.is_superuser">
          <el-menu-item index="/admin">
            <el-icon><UserFilled /></el-icon>
            <span>管理员工作台</span>
          </el-menu-item>
          <el-menu-item index="/admin/review">
            <el-icon><Checked /></el-icon>
            <span>待审核知识点</span>
          </el-menu-item>
          <el-menu-item index="/admin/knowledge">
            <el-icon><Collection /></el-icon>
            <span>知识库管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/logs">
            <el-icon><Tickets /></el-icon>
            <span>系统日志</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ route.meta.title || "" }}</div>
        <el-dropdown @command="handleCommand">
          <span class="user-chip">
            <el-avatar :size="28" class="avatar">
              {{ (auth.user?.full_name || auth.user?.nickname || auth.user?.email || "?")[0] }}
            </el-avatar>
            <span class="user-name">{{ auth.user?.full_name || auth.user?.nickname || auth.user?.email }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings">
                <el-icon><Setting /></el-icon>个人设置
              </el-dropdown-item>
              <el-dropdown-item divided command="logout">
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessageBox, ElMessage } from "element-plus"
import { useAuthStore } from "@/stores/auth"
import { homeworkApi } from "@/api"
import type { Homework } from "@/types"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 作业区（列表/编辑/批改/看板）统一高亮「作业管理」
const activeMenu = computed(() => {
  if (route.path.startsWith("/homework")) return "/homework"
  return route.path
})

async function handleMenuSelect(index: string) {
  if (index === "smart-grading") {
    await goSmartGrading()
    return
  }
  router.push(index)
}

// 「智能批改」快捷入口：自动定位到最近一个已发布作业的批改页
async function goSmartGrading() {
  try {
    const { data } = await homeworkApi.list({ limit: 100 })
    const items: Homework[] = data.data ?? []
    const target = items.find((h) => h.status === "published")
    if (target) {
      router.push(`/homework/${target.id}/grading`)
      return
    }
    ElMessage.info("还没有已发布的作业，请先到「作业管理」发布作业")
    router.push("/homework")
  } catch {
    router.push("/homework")
  }
}

async function handleCommand(cmd: string) {
  if (cmd === "logout") {
    await ElMessageBox.confirm("确定退出登录吗？", "提示", { type: "warning" })
    auth.logout()
    router.push("/login")
  } else if (cmd === "settings") {
    router.push("/settings")
  }
}
</script>

<style scoped>
.layout {
  height: 100%;
}

.aside {
  background: #1f2430;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 20px;
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo-icon {
  font-size: 20px;
}

.menu {
  border-right: none;
  flex: 1;
}

.menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #ec4899, #d946ef);
}

.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  height: 56px;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none;
}

.avatar {
  background: #ec4899;
  color: #fff;
  font-weight: 600;
}

.user-name {
  font-size: 14px;
  color: #303133;
}

.main {
  padding: 20px;
  overflow-y: auto;
}
</style>
