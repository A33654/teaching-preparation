<template>
  <div>
    <div class="page-header">
      <div>
        <h1>我的教案</h1>
        <div class="subtitle">章节驱动智能生成：选择章节，系统自动联动知识图谱</div>
      </div>
      <el-button type="primary" :icon="MagicStick" @click="$router.push('/new-lesson')">新建备课</el-button>
    </div>

    <div class="card-panel">
      <el-table v-loading="loading" :data="plans" stripe>
        <el-table-column prop="title" label="标题" min-width="200">
          <template #default="{ row }"><b>{{ row.title }}</b></template>
        </el-table-column>
        <el-table-column prop="subject" label="学科" width="100" />
        <el-table-column label="学段" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.grade_level" size="small" effect="plain">{{ row.grade_level }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="关联知识点" width="140">
          <template #default="{ row }">
            <el-tooltip v-if="row.knowledge_points.length" :content="row.knowledge_points.map((k: any) => k.name).join('、')">
              <el-tag size="small" type="warning" effect="plain">{{ row.knowledge_points.length }} 个</el-tag>
            </el-tooltip>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="router.push(`/lesson-plans/${row.id}/edit`)">
              编辑
            </el-button>
            <el-button size="small" plain :icon="Download" @click="exportDocx(row)">
              导出 Word
            </el-button>
            <el-popconfirm title="确定删除该教案？" @confirm="remove(row)">
              <template #reference>
                <el-button size="small" type="danger" plain :icon="Delete" />
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detailPlan?.title" size="55%">
      <template v-if="detailPlan">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="学科">{{ detailPlan.subject }}</el-descriptions-item>
          <el-descriptions-item label="学段">{{ detailPlan.grade_level || "—" }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(detailPlan.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detailPlan.knowledge_points.length" style="margin-bottom: 16px">
          <el-tag
            v-for="kp in detailPlan.knowledge_points"
            :key="kp.id"
            type="warning"
            effect="plain"
            style="margin-right: 6px"
          >
            {{ kp.name }}
          </el-tag>
        </div>

        <h4 class="section-title">教学目标</h4>
        <div class="lp-text">{{ detailPlan.teaching_objectives || "—" }}</div>

        <h4 class="section-title">教学过程</h4>
        <div class="lp-text">{{ detailPlan.teaching_process || "—" }}</div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { Delete, Download, MagicStick } from "@element-plus/icons-vue"
import { authorizedFetch, lessonPlansApi } from "@/api"
import type { LessonPlan } from "@/types"

const router = useRouter()
const plans = ref<LessonPlan[]>([])
const loading = ref(false)

const detailVisible = ref(false)
const detailPlan = ref<LessonPlan | null>(null)

async function load() {
  loading.value = true
  try {
    const resp = await lessonPlansApi.list({ limit: 100 })
    plans.value = resp.data.data
  } finally {
    loading.value = false
  }
}

function openDetail(row: LessonPlan) {
  detailPlan.value = row
  detailVisible.value = true
}

function exportDocx(row: LessonPlan) {
  authorizedFetch(lessonPlansApi.exportUrl(row.id))
    .then((r) => {
      if (r.status === 401) return // 已跳转登录页
      if (!r.ok) throw new Error("导出失败")
      return r.blob()
    })
    .then((blob) => {
      if (!blob) return
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${row.title}.docx`
      a.click()
      URL.revokeObjectURL(url)
    })
    .catch(() => ElMessage.error("导出失败"))
}

async function remove(row: LessonPlan) {
  await lessonPlansApi.remove(row.id)
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
  color: #c0c4cc;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.section-title {
  margin: 14px 0 8px;
  font-size: 14px;
  color: #303133;
  border-left: 3px solid #ec4899;
  padding-left: 8px;
}

.lp-text {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.9;
  color: #606266;
  white-space: pre-wrap;
}
</style>
