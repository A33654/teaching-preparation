<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-icon">📚</span>
        <span class="logo-text">AI 教学助手</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="menu"
        background-color="#1f2430"
        text-color="#a3a8b8"
        active-text-color="#ffffff"
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
          <el-menu-item index="/documents">
            <el-icon><Folder /></el-icon>
            <span>我的素材库</span>
          </el-menu-item>
          <el-menu-item index="/ppt">
            <el-icon><Film /></el-icon>
            <span>PPT 生成</span>
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
import { ElMessageBox } from "element-plus"
import { useAuthStore } from "@/stores/auth"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)

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
