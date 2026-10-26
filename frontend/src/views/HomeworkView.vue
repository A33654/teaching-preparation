<template>
  <div class="wrap">
    <div class="head">
      <h3>作业管理</h3>
      <div class="spacer" />
      <el-button @click="load" :loading="loading">刷新</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="tip"
      title="从教案一键生成作业：进入某份教案 → 点击「生成作业」，系统会以该教案课堂习题为初始题目并自动继承知识点。"
    />

    <el-table :data="list" v-loading="loading" border style="width: 100%">
      <el-table-column prop="title" label="作业标题" min-width="220" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'published' ? 'success' : 'info'">
            {{ row.status === "published" ? "已发布" : row.status === "closed" ? "已关闭" : "草稿" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="题目数" width="90">
        <template #default="{ row }">{{ row.questions.length }}</template>
      </el-table-column>
      <el-table-column label="知识点" min-width="180">
        <template #default="{ row }">
          <el-tag
            v-for="kp in row.knowledge_points.slice(0, 4)"
            :key="kp.id"
            size="small"
            type="info"
            class="kp"
          >
            {{ kp.name }}
          </el-tag>
          <span v-if="!row.knowledge_points.length" class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">
          {{ row.updated_at ? new Date(row.updated_at).toLocaleString() : "—" }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="edit(row.id)">编辑</el-button>
          <el-button size="small" type="success" @click="grading(row.id)">批改</el-button>
          <el-button size="small" type="warning" @click="analytics(row.id)">看板</el-button>
          <el-button
            size="small"
            type="info"
            :disabled="row.status !== 'published'"
            @click="closeHomework(row)"
          >
            截止
          </el-button>
          <el-button size="small" @click="goLessonPlan(row)" :disabled="!row.lesson_plan_id">
            来源教案
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!list.length && !loading" class="empty">暂无作业，请到教案页点击「生成作业」。</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { homeworkApi } from "@/api"
import type { Homework } from "@/types"

const router = useRouter()
const list = ref<Homework[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await homeworkApi.list({ limit: 100 })
    list.value = data.data
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function edit(id: string) {
  router.push(`/homework/${id}/edit`)
}

function grading(id: string) {
  router.push(`/homework/${id}/grading`)
}

function analytics(id: string) {
  router.push(`/homework/${id}/analytics`)
}

function goLessonPlan(row: Homework) {
  if (row.lesson_plan_id) router.push(`/lesson-plans/${row.lesson_plan_id}/edit`)
}

// PRD §4 / §9 R-3：手动截止（截止后不再接受提交）
async function closeHomework(row: Homework) {
  try {
    await ElMessageBox.confirm(
      `确认将作业「${row.title}」置为已截止？截止后不再接受新的提交。`,
      "截止确认",
      { type: "warning", confirmButtonText: "确认截止", cancelButtonText: "取消" },
    )
  } catch {
    return
  }
  try {
    await homeworkApi.close(row.id)
    ElMessage.success("作业已截止")
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

<style scoped>
.wrap { max-width: 1200px; margin: 0 auto; padding: 8px 0 40px; }
.head { display: flex; align-items: center; margin-bottom: 12px; }
.head h3 { margin: 0; font-size: 18px; }
.spacer { flex: 1; }
.tip { margin-bottom: 12px; }
.kp { margin-right: 4px; }
.muted { color: #c0c4cc; }
.empty { color: #909399; text-align: center; padding: 40px 0; font-size: 13px; }
</style>
