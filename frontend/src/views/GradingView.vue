<template>
  <div class="wrap">
    <div class="head">
      <el-button size="small" @click="router.back()">← 返回</el-button>
      <h3>智能批改 · {{ hw?.title || "加载中" }}</h3>
      <div class="spacer" />
      <el-button size="small" @click="runVerify" :loading="verifying">FR-04 标注集验收</el-button>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="tip"
      title="客观题（选择/填空）由规则 + 标准答案自动判分并给出解析；主观题由 AI 给出建议分/评语/知识点/置信度，终评必须经教师二次确认，确认后不可修改。"
    />

    <div v-if="!subs.length && !loading" class="empty">该作业暂无提交，请到作业编辑页先「模拟提交」。</div>

    <template v-else>
      <!-- 提交选择 -->
      <el-card class="sub-card">
        <template #header>
          <div class="card-head">
            <span>选择提交（学号哈希）</span>
            <div class="spacer" />
            <el-button type="primary" size="small" :loading="grading" @click="doGrade">
              触发自动判分
            </el-button>
          </div>
        </template>
        <el-radio-group v-model="subId" size="small" @change="loadGrades">
          <el-radio-button v-for="s in subs" :key="s.id" :value="s.id">
            {{ s.student_id_hash.slice(0, 8) }}…
            <el-tag v-if="s.status === 'graded'" size="small" type="success" class="inline-tag">已判分</el-tag>
          </el-radio-button>
        </el-radio-group>
      </el-card>

      <!-- 汇总 -->
      <div v-if="grades.length" class="summary">
        <el-tag type="success">客观题正确 {{ objCorrect }}/{{ objTotal }}</el-tag>
        <el-tag type="warning">待教师终评 {{ pendingFinalize }}</el-tag>
        <el-tag type="info">已确认 {{ finalizedCount }}（不可改）</el-tag>
        <el-tag v-if="humanCount" type="danger">建议人工 {{ humanCount }}</el-tag>
      </div>

      <div v-if="!grades.length && !grading" class="empty">尚未判分，点击右上角「触发自动判分」。</div>

      <!-- 逐题判分 -->
      <el-card v-for="(g, i) in rows" :key="g.question_id" class="q-card">
        <template #header>
          <div class="card-head">
            <b>第 {{ i + 1 }} 题</b>
            <el-tag size="small">{{ typeText(g.question_type) }}</el-tag>
            <span class="full">满分 {{ g.full_score }}</span>
            <div class="spacer" />
            <el-tag v-if="g.finalized" size="small" type="info">已确认不可改</el-tag>
            <el-tag v-else-if="g.needs_human" size="small" type="danger">建议人工</el-tag>
            <el-tag v-else size="small" type="warning">待终评</el-tag>
          </div>
        </template>

        <div class="stem">{{ questionOf(g.question_id)?.stem || "（题目已删除）" }}</div>

        <div class="answer">
          学生作答：<b>{{ answerOf(g.question_id) }}</b>
        </div>

        <!-- 客观题：自动判分 + 溯源 -->
        <div v-if="isObjective(g.question_type)" class="block">
          <el-tag :type="g.is_correct ? 'success' : 'danger'" size="small">
            {{ g.is_correct ? "判为正确" : "判为错误" }}
          </el-tag>
          <span class="score">自动得分 {{ g.auto_score }} / {{ g.full_score }}</span>
          <div class="detail">判分依据（可溯源）：{{ g.auto_detail }}</div>
        </div>

        <!-- 主观题：AI 建议 -->
        <div v-else class="block ai">
          <div class="ai-row">
            <span>AI 建议分</span>
            <b class="ai-score">{{ g.ai_suggested_score }}</b>
            <span class="muted">/ {{ g.full_score }}</span>
            <div class="spacer" />
            <span class="muted">置信度</span>
            <el-progress
              class="conf"
              :percentage="Math.round((g.ai_confidence ?? 0) * 100)"
              :stroke-width="10"
              :color="(g.ai_confidence ?? 0) < 0.7 ? '#e6a23c' : '#67c23a'"
              style="width: 120px"
            />
            <el-tag size="small" :type="(g.ai_confidence ?? 0) < 0.7 ? 'warning' : 'success'">
              {{ (g.ai_confidence ?? 0).toFixed(2) }}
            </el-tag>
          </div>
          <div class="detail">批改评语：{{ g.ai_comment }}</div>
          <div class="detail muted">
            命中知识点：{{ g.ai_knowledge_points.length ? g.ai_knowledge_points.join("、") : "—" }}
          </div>
          <el-alert
            v-if="g.ai_unavailable"
            class="notice"
            type="error"
            :closable="false"
            show-icon
            title="AI 不可用，转人工：该建议为离线兜底结果，终评必须由教师手填，不可一键采纳。"
          />
          <el-alert
            v-else-if="g.needs_human"
            class="notice"
            type="warning"
            :closable="false"
            show-icon
            title="置信度低于 0.7，已强制标记「建议人工」，请重点复核后再确认终评。"
          />
        </div>

        <!-- FR-06 教师复核与终评 -->
        <el-divider content-position="left">教师终评</el-divider>

        <template v-if="g.finalized">
          <div class="final">
            <el-tag type="success" size="small">终评分 {{ g.final_score }} / {{ g.full_score }}</el-tag>
            <span class="detail">评语：{{ g.final_comment || "—" }}</span>
            <span class="muted">· 已确认不可改（{{ g.finalized_at ? new Date(g.finalized_at).toLocaleString() : "" }}）</span>
          </div>
        </template>

        <template v-else>
          <div class="edit">
            <span class="label">终评分</span>
            <el-input-number
              v-model="editOf(g).score"
              :min="0"
              :max="Number(g.full_score)"
              :step="0.5"
              size="small"
              controls-position="right"
            />
            <el-button
              v-if="!isObjective(g.question_type) && g.ai_suggested_score != null"
              size="small"
              type="primary"
              :disabled="!canAdopt(g)"
              :title="adoptHint(g)"
              @click="adopt(g)"
            >
              一键采纳建议（{{ g.ai_suggested_score }} 分）
            </el-button>
            <div class="spacer" />
            <el-button size="small" type="success" @click="submitFinal(g)">提交终评</el-button>
          </div>
          <el-input
            v-model="editOf(g).comment"
            type="textarea"
            :rows="2"
            placeholder="批改评语（可选）"
          />
        </template>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { gradingApi, homeworkApi } from "@/api"
import type { FinalizeGradeRequest, Homework, QuestionGrade, Submission } from "@/types"

const route = useRoute()
const router = useRouter()
const homeworkId = String(route.params.homeworkId || "")

const hw = ref<Homework | null>(null)
const subs = ref<Submission[]>([])
const subId = ref<string>("")
const grades = ref<QuestionGrade[]>([])
const loading = ref(false)
const grading = ref(false)
const verifying = ref(false)
const editMap = reactive<Record<string, { score: number | null; comment: string }>>({})

// 学生提交的题目顺序：按作业题目顺序展示判分行
const rows = computed(() => {
  const qids = (hw.value?.questions || []).map((q) => q.id)
  const extra = grades.value.filter((g) => !qids.includes(g.question_id))
  const ordered = qids
    .map((id) => grades.value.find((g) => g.question_id === id))
    .filter(Boolean) as QuestionGrade[]
  return [...ordered, ...extra]
})

const objGrades = computed(() => grades.value.filter((g) => isObjective(g.question_type)))
const objTotal = computed(() => objGrades.value.length)
const objCorrect = computed(() => objGrades.value.filter((g) => g.is_correct).length)
const pendingFinalize = computed(() => grades.value.filter((g) => !g.finalized).length)
const finalizedCount = computed(() => grades.value.filter((g) => g.finalized).length)
const humanCount = computed(() => grades.value.filter((g) => g.needs_human && !g.finalized).length)

function isObjective(t: string) {
  return t === "choice" || t === "fill"
}
function typeText(t: string) {
  return { choice: "选择", fill: "填空", short: "简答", essay: "论述" }[t] || t
}
function questionOf(qid: string) {
  return (hw.value?.questions || []).find((q) => q.id === qid)
}
function answerOf(qid: string) {
  const cur = subs.value.find((s) => s.id === subId.value)
  const a = (cur?.answers || []).find((x) => x.question_id === qid)
  return a && a.content !== "" && a.content != null ? String(a.content) : "（未作答）"
}

// 每题的编辑态（终评分/评语），缺省以自动判分或 AI 建议预填
function editOf(g: QuestionGrade) {
  if (!editMap[g.question_id]) {
    editMap[g.question_id] = {
      score: g.auto_score ?? g.ai_suggested_score ?? 0,
      comment: "",
    }
  }
  return editMap[g.question_id]
}

async function load() {
  loading.value = true
  try {
    const { data } = await homeworkApi.get(homeworkId)
    hw.value = data
    const sr = await homeworkApi.submissions(homeworkId)
    subs.value = sr.data.data
    if (!subId.value && subs.value.length) subId.value = subs.value[0].id
    await loadGrades()
  } finally {
    loading.value = false
  }
}

async function loadGrades() {
  if (!subId.value) return
  const { data } = await gradingApi.grades(homeworkId, subId.value)
  grades.value = data.data
  for (const g of data.data) {
    if (!editMap[g.question_id]) editMap[g.question_id] = { score: g.auto_score ?? g.ai_suggested_score ?? 0, comment: "" }
  }
}

async function doGrade() {
  if (!subId.value) return
  grading.value = true
  try {
    const { data } = await gradingApi.grade(homeworkId, subId.value)
    grades.value = data.grades
    for (const g of data.grades) {
      editMap[g.question_id] = { score: g.auto_score ?? g.ai_suggested_score ?? 0, comment: "" }
    }
    await load() // 刷新提交状态为已判分
    ElMessage.success(data.message || "判分完成")
  } catch {
    // 拦截器已提示
  } finally {
    grading.value = false
  }
}

// PRD §7①②：AI 不可用或低置信度时禁止一键采纳（后端同规则，此处仅做前置拦截）
function canAdopt(g: QuestionGrade) {
  if (g.ai_suggested_score == null) return false
  if (g.ai_unavailable) return false
  return (g.ai_confidence ?? 0) >= 0.7
}

function adoptHint(g: QuestionGrade) {
  if (g.ai_unavailable) return "AI 不可用，该题为离线兜底建议，请手填终评"
  if ((g.ai_confidence ?? 0) < 0.7) return "低置信度建议，终评必须由教师手填"
  return ""
}

// FR-06：一键采纳 AI 建议（二次确认 → 落库，不可逆）
async function adopt(g: QuestionGrade) {
  const idx = rows.value.findIndex((r) => r.question_id === g.question_id) + 1
  try {
    await ElMessageBox.confirm(
      `确认采纳第 ${idx} 题的 AI 建议分 ${g.ai_suggested_score} 分？提交后不可再修改。`,
      "二次确认",
      { type: "warning", confirmButtonText: "确认提交", cancelButtonText: "取消" },
    )
  } catch {
    return // 用户取消
  }
  await postFinalize(g, {
    adopt_suggestion: true,
    final_comment: editMap[g.question_id]?.comment || null,
    confirm: true,
  })
}

// FR-06：手动改分 + 写评语（二次确认 → 落库，不可逆）
async function submitFinal(g: QuestionGrade) {
  const idx = rows.value.findIndex((r) => r.question_id === g.question_id) + 1
  const score = editMap[g.question_id]?.score
  if (score == null) {
    ElMessage.warning("请先填写终评分")
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认提交第 ${idx} 题终评分 ${score} 分？该操作不可逆，提交后不可再修改。`,
      "二次确认",
      { type: "warning", confirmButtonText: "确认提交", cancelButtonText: "取消" },
    )
  } catch {
    return
  }
  await postFinalize(g, {
    final_score: score,
    final_comment: editMap[g.question_id]?.comment || null,
    confirm: true,
  })
}

async function postFinalize(g: QuestionGrade, payload: FinalizeGradeRequest) {
  try {
    const { data } = await gradingApi.finalize(homeworkId, subId.value, g.question_id, payload)
    const i = grades.value.findIndex((x) => x.question_id === g.question_id)
    if (i >= 0) grades.value[i] = data
    ElMessage.success("终评已确认，不可修改")
  } catch {
    // 拦截器已提示（含 409 已确认不可改）
  }
}

// FR-04：标注集验收
async function runVerify() {
  verifying.value = true
  try {
    const { data } = await gradingApi.verifyLabeledSet()
    const pct = (data.accuracy * 100).toFixed(2)
    ElMessageBox.alert(
      `标注集规模：${data.total} 题\n判分正确：${data.correct} 题\n准确率：${pct}%（验收线 ${data.threshold * 100}%）\n错判条数：${data.misjudged.length}（每条含判分依据，可溯源）`,
      "FR-04 客观题自动判分验收",
      { type: data.passed ? "success" : "error", confirmButtonText: "知道了" },
    )
  } catch {
    // 拦截器已提示
  } finally {
    verifying.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.wrap {
  max-width: 960px;
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
.sub-card {
  margin-bottom: 12px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.inline-tag {
  margin-left: 6px;
  transform: translateY(-1px);
}
.summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.q-card {
  margin-bottom: 12px;
}
.full {
  font-size: 12px;
  color: #909399;
}
.stem {
  font-size: 14px;
  margin-bottom: 6px;
  line-height: 1.6;
}
.answer {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}
.block {
  background: #f7f9fc;
  border-radius: 6px;
  padding: 10px;
  font-size: 13px;
}
.ai {
  background: #f4f9ff;
}
.ai-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.ai-score {
  color: #409eff;
  font-size: 16px;
}
.score {
  margin-left: 8px;
  color: #606266;
}
.detail {
  margin-top: 6px;
  line-height: 1.6;
  color: #606266;
}
.muted {
  color: #909399;
}
.notice {
  margin-top: 8px;
}
.conf {
  margin: 0 4px;
}
.edit {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.label {
  font-size: 13px;
  color: #606266;
}
.final {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}
.empty {
  color: #909399;
  font-size: 13px;
  padding: 20px;
  text-align: center;
}
</style>
