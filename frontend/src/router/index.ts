import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "@/stores/auth"
import { TOKEN_KEY } from "@/api"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { title: "登录" },
    },
    {
      path: "/signup",
      name: "signup",
      component: () => import("@/views/SignupView.vue"),
      meta: { title: "注册" },
    },
    {
      path: "/recover-password",
      name: "recover-password",
      component: () => import("@/views/RecoverPasswordView.vue"),
      meta: { title: "找回密码" },
    },
    {
      path: "/reset-password",
      name: "reset-password",
      component: () => import("@/views/ResetPasswordView.vue"),
      meta: { title: "重置密码" },
    },
    {
      path: "/",
      component: () => import("@/layouts/DefaultLayout.vue"),
      children: [
        // ==================== 教师端 ====================
        {
          path: "",
          name: "dashboard",
          component: () => import("@/views/DashboardView.vue"),
          meta: { title: "工作台" },
        },
        {
          path: "new-lesson",
          name: "new-lesson",
          component: () => import("@/views/NewLessonView.vue"),
          meta: { title: "新建备课任务" },
        },
        {
          path: "lesson-plans",
          name: "lesson-plans",
          component: () => import("@/views/LessonPlansView.vue"),
          meta: { title: "我的教案" },
        },
        {
          path: "lesson-plans/:id/edit",
          name: "lesson-plan-edit",
          component: () => import("@/views/LessonPlanEditView.vue"),
          meta: { title: "教案编辑" },
        },
        {
          path: "documents",
          name: "documents",
          component: () => import("@/views/DocumentsView.vue"),
          meta: { title: "我的素材库" },
        },
        {
          path: "chat",
          name: "chat",
          redirect: "/lesson-plans",
        },
        {
          path: "knowledge-graph",
          name: "knowledge-graph",
          component: () => import("@/views/KnowledgeGraphView.vue"),
          meta: { title: "知识图谱" },
        },
        {
          path: "ppt",
          name: "ppt",
          component: () => import("@/views/PptView.vue"),
          meta: { title: "PPT 生成" },
        },
        {
          path: "settings",
          name: "settings",
          component: () => import("@/views/SettingsView.vue"),
          meta: { title: "个人设置" },
        },
        // ==================== 管理员后台 ====================
        {
          path: "admin",
          name: "admin",
          component: () => import("@/views/admin/AdminDashboardView.vue"),
          meta: { title: "管理员工作台", requiresSuperuser: true },
        },
        {
          path: "admin/review",
          name: "admin-review",
          component: () => import("@/views/admin/AdminReviewView.vue"),
          meta: { title: "待审核知识点", requiresSuperuser: true },
        },
        {
          path: "admin/knowledge",
          name: "admin-knowledge",
          component: () => import("@/views/admin/AdminKnowledgeView.vue"),
          meta: { title: "知识库管理", requiresSuperuser: true },
        },
        {
          path: "admin/logs",
          name: "admin-logs",
          component: () => import("@/views/admin/AdminLogsView.vue"),
          meta: { title: "系统日志", requiresSuperuser: true },
        },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
})

// 路由守卫：未登录跳转登录页
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const hasToken = !!localStorage.getItem(TOKEN_KEY)

  const publicPages = ["login", "signup", "recover-password", "reset-password"]
  if (publicPages.includes(String(to.name))) {
    if (hasToken && to.name !== "reset-password") return { name: "dashboard" }
    return true
  }

  if (!hasToken) {
    return { name: "login", query: { redirect: to.fullPath } }
  }
  if (!auth.user) {
    await auth.fetchMe()
  }
  // 角色隔离：管理员只进管理后台，教师只进教师端
  const isAdmin = !!auth.user?.is_superuser
  const isAdminRoute = String(to.path).startsWith("/admin")
  if (isAdminRoute && !isAdmin) {
    return { name: "dashboard" }
  }
  if (!isAdminRoute && isAdmin && to.name !== "settings") {
    return { name: "admin" }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · AI 教学助手` : "AI 教学助手"
})

export default router
