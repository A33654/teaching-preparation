<template>
  <div class="wrap">
    <div class="head">
      <el-button size="small" @click="router.back()">← 返回</el-button>
      <h3>错误聚合看板 · {{ hwTitle }}</h3>
      <div class="spacer" />
      <el-button size="small" type="primary" :loading="exporting !== ''" @click="download('xlsx')">
        导出 Excel
      </el-button>
      <el-button size="small" :loading="exporting !== ''" @click="download('pdf')">导出 PDF</el-button>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="tip"
      title="按关联知识点统计错误率与高频错误模式；错误率 ≥ 阈值的知识点会推送「建议补入图谱误区」卡片，教师确认后回流写入图谱。导出文件仅含学号哈希与匿名昵称，不含任何明文身份。"
    />

    <!-- 视角切换 -->
    <el-card class="scope-card">
      <template #header>
        <div class="card-head">
          <span>统计视角</span>
          <div class="spacer" />
          <el-tag type="info" size="small">
            覆盖知识点 {{ dash?.knowledge_point_total ?? 0 }} 个
          </el-tag>
        </div>
      </template>
      <el-radio-group v-model="scope" size="small" @change="onScopeChange">
        <el-radio-button value="class">班级视角</el-radio-button>
        <el-radio-button value="personal">个人视角</el-radio-button>
      </el-radio-group>
      <el-select
        v-if="scope === 'personal'"
        v-model="subId"
        size="small"
        class="sub-select"
        placeholder="选择学生提交"
        @change="loadDashboard"
      >
        <el-option v-for="s in subs" :key="s.id" :value="s.id" :label="s.student_id_hash.slice(0, 10) + '…'" />
      </el-select>
    </el-card>

    <!-- FR-07 知识点错误聚合 -->
    <el-card class="table-card">
      <template #header>
        <div class="card-head">
          <span>知识点错误率（{{ rows.length }}）</span>
          <div class="spacer" />
          <span class="muted">提交 {{ dash?.graded_submissions ?? 0 }} / {{ dash?.total_submissions ?? 0 }}</span>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" border stripe size="small">
        <el-table-column label="知识点" min-width="150">
          <template #default="{ row }">
            {{ row.knowledge_point_name || row.knowledge_point_id }}
            <div class="kp-id">{{ row.knowledge_point_id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="question_count" label="关联题目" width="90" align="center" />
        <el-table-column prop="graded_count" label="已批改题次" width="100" align="center" />
        <el-table-column prop="wrong_count" label="错误次数" width="90" align="center" />
        <el-table-column label="错误率" min-width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round(row.error_rate * 100)"
              :stroke-width="12"
              :color="rateColor(row.error_rate)"
            />
          </template>
        </el-table-column>
        <el-table-column label="TOP 高频错误模式" min-width="260">
          <template #default="{ row }">
            <div v-if="!row.top_patterns.length" class="muted">
              {{ row.graded_count ? "无错误" : "暂无作答" }}
            </div>
            <div v-for="p in row.top_patterns" :key="p.expression" class="pattern">
              <el-tag size="small" type="danger">{{ p.count }} 次</el-tag>
              <span>{{ p.expression }}</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- FR-08 误区回流建议 -->
    <el-card class="card">
      <template #header>
        <div class="card-head">
          <span>误区回流建议（阈值 {{ (suggestions?.threshold ?? 0.4) * 100 }}%）</span>
          <div class="spacer" />
          <el-tag size="small" :type="suggestions?.count ? 'warning' : 'success'">
            {{ suggestions?.count ?? 0 }} 条待确认
          </el-tag>
        </div>
      </template>

      <div v-if="!suggestions?.count" class="empty">暂无错误率达标的知识点。</div>

      <div v-for="s in suggestions?.data || []" :key="s.knowledge_point_id" class="mis-card">
        <div class="mis-head">
          <b>{{ s.knowledge_point_name || s.knowledge_point_id }}</b>
          <el-tag size="small" type="danger">错误率 {{ (s.error_rate * 100).toFixed(0) }}%</el-tag>
          <el-tag size="small" type="info">{{ s.wrong_count }}/{{ s.graded_count }}</el-tag>
        </div>
        <div class="mis-body">
          <div><span class="label">典型错误表述</span></div>
          <div v-for="e in s.typical_expressions" :key="e" class="expr">· {{ e }}</div>
          <div class="sug"><span class="label">建议误区</span>{{ s.suggested_content }}</div>
          <div class="sug"><span class="label">建议纠正</span>{{ s.suggested_correction || "—" }}</div>
        </div>
        <el-button
          size="small"
          type="primary"
          class="confirm-btn"
          :loading="confirming === s.knowledge_point_id"
          @click="confirmBackflow(s)"
        >
          确认补入图谱误区
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { analyticsApi, authorizedFetch, homeworkApi } from "@/api"
import type { ErrorDashboard, KnowledgePointErrorStat, MisconceptionSuggestion, MisconceptionSuggestions } from "@/types"

const route = useRoute()
const router = useRouter()
const homeworkId = String(route.params.homeworkId || "")

const hwTitle = ref("")
const scope = ref<"class" | "personal">("class")
const subId = ref<string>("")
const subs = ref<{ id: string; student_id_hash: string }[]>([])
const dash = ref<ErrorDashboard | null>(null)
const suggestions = ref<MisconceptionSuggestions | null>(null)
const loading = ref(false)
const exporting = ref("")
const confirming = ref("")

const rows = computed<KnowledgePointErrorStat[]>(() => dash.value?.knowledge_points || [])

function rateColor(rate: number) {
  if (rate >= 0.4) return "#e24b4a"
  if (rate > 0) return "#ef9f27"
  return "#67c23a"
}

async function load() {
  await Promise.all([loadMeta(), loadDashboard(), loadSuggestions()])
}

async function loadMeta() {
  const { data } = await homeworkApi.get(homeworkId)
  hwTitle.value = data.title
  subs.value = (await homeworkApi.submissions(homeworkId)).data.data
  if (!subId.value && subs.value.length) subId.value = subs.value[0].id
}

async function loadDashboard() {
  loading.value = true
  try {
    const params: Record<string, string> = { scope: scope.value }
    if (scope.value === "personal") params.submission_id = subId.value
    const { data } = await analyticsApi.dashboard(homeworkId, params)
    dash.value = data
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function loadSuggestions() {
  const { data } = await analyticsApi.suggestions(homeworkId)
  suggestions.value = data
}

function onScopeChange() {
  loadDashboard()
}

async function confirmBackflow(s: MisconceptionSuggestion) {
  try {
    await ElMessageBox.confirm(
      `确认为知识点「${s.knowledge_point_name || s.knowledge_point_id}」补入误区与纠正？写入后来源将标注「教学回流」。`,
      "二次确认",
      { type: "warning", confirmButtonText: "确认写入", cancelButtonText: "取消" },
    )
  } catch {
    return
  }
  confirming.value = s.knowledge_point_id
  try {
    const { data } = await analyticsApi.confirmBackflow(homeworkId, {
      knowledge_point_id: s.knowledge_point_id,
      content: s.suggested_content,
      correction: s.suggested_correction,
    })
    ElMessage.success(`已写入图谱误区（来源：${data.source}）`)
    await loadSuggestions()
  } catch {
    // 拦截器已提示
  } finally {
    confirming.value = ""
  }
}

async function download(format: "xlsx" | "pdf") {
  exporting.value = format
  try {
    const url = analyticsApi.exportUrl(
      homeworkId,
      format,
      scope.value,
      scope.value === "personal" ? subId.value : undefined,
    )
    const resp = await authorizedFetch(url)
    if (!resp.ok) throw new Error(String(resp.status))
    const blob = await resp.blob()
    const link = document.createElement("a")
    link.href = URL.createObjectURL(blob)
    link.download = `批改-${homeworkId.slice(0, 8)}.${format}`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success("导出已开始下载（内容已脱敏）")
  } catch {
    ElMessage.error("导出失败，请重试")
  } finally {
    exporting.value = ""
  }
}

onMounted(load)
</script>

<style scoped>
.wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.head h3 {
  margin: 0;
  font-size: 17px;
}
.spacer {
  flex: 1;
}
.tip {
  margin-bottom: 12px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.scope-card,
.card {
  margin-bottom: 12px;
}
.table-card {
  margin-bottom: 12px;
}
.sub-select {
  margin-left: 12px;
  width: 240px;
}
.kp-id {
  font-size: 11px;
  color: #a8abb2;
}
.pattern {
  display: flex;
  align-items: center;
  gap: 6px;
  line-height: 1.7;
  font-size: 12px;
}
.muted {
  color: #909399;
}
.empty {
  color: #909399;
  font-size: 13px;
  padding: 16px;
  text-align: center;
}
.mis-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  background: #fffaf5;
}
.mis-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.mis-body {
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}
.label {
  color: #909399;
  margin-right: 6px;
}
.expr {
  padding-left: 8px;
  color: #c45656;
}
.sug {
  margin-top: 4px;
}
.confirm-btn {
  margin-top: 8px;
}
</style>
