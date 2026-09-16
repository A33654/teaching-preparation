<template>
  <div class="unified-wrap">
    <div class="head">
      <h1>智能备课工作台</h1>
      <div class="subtitle">选择章节，系统自动联动知识图谱生成教案——无需手动选择知识点</div>
    </div>

    <div class="columns">
      <!-- ============ 左栏：备课信息 ============ -->
      <div class="left">
        <el-card class="panel">
          <template #header>① 备课基础信息</template>
          <el-form label-width="90px" label-position="left">
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="学科" required>
                  <el-select v-model="form.subject" placeholder="选择学科" style="width: 100%">
                    <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.name" />
                    <el-option label="数学" value="数学" />
                    <el-option label="语文" value="语文" />
                    <el-option label="物理" value="物理" />
                    <el-option label="化学" value="化学" />
                    <el-option label="英语" value="英语" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="年级" required>
                  <el-select v-model="form.gradeLevel" placeholder="选择年级" style="width: 100%">
                    <el-option v-for="g in ['小学', '初中', '高中']" :key="g" :label="g" :value="g" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="教材版本">
                  <el-select
                    v-model="form.textbookVersion"
                    placeholder="选择教材（可留空）"
                    clearable
                    filterable
                    allow-create
                    style="width: 100%"
                  >
                    <el-option v-for="t in textbookVersions" :key="t" :label="t" :value="t" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="单元 / 章节" required>
                  <el-input
                    v-model="form.chapter"
                    placeholder="如：《光的反射》"
                    @blur="loadChapterContext"
                    @keyup.enter="loadChapterContext"
                  >
                    <template #append>
                      <el-button :loading="contextLoading" @click="loadChapterContext">加载</el-button>
                    </template>
                  </el-input>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-card>

        <el-card class="panel">
          <template #header>② 个性化备课需求</template>
          <el-input
            v-model="form.requirements"
            type="textarea"
            :rows="4"
            placeholder="例如：课堂要生动有趣，附带课堂习题和板书设计，重点讲解易错点"
          />
        </el-card>

        <el-card class="panel">
          <template #header>③ 自定义素材上传（可选）</template>
          <el-upload
            :show-file-list="true"
            :auto-upload="false"
            accept=".pdf,.docx,.txt"
            :on-change="onFileChange"
            :limit="1"
          >
            <el-button :icon="Upload">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">
                上传材料只增强 RAG 检索（教材原文 / 补充讲义），不影响知识图谱主流程；
                抽取到的知识点自动进入管理员待审核队列
              </div>
            </template>
          </el-upload>
        </el-card>

        <div class="gen-row">
          <el-button
            type="primary"
            size="large"
            class="gen-btn"
            :loading="generating"
            @click="submit"
          >
            ⚡ 一键智能生成教案
          </el-button>
        </div>
      </div>

      <!-- ============ 右栏：本节备课参考（图谱计算的业务清单，只读） ============ -->
      <div class="right">
        <el-card class="panel">
          <template #header>
            <div class="ref-head">
              <span>本节备课参考</span>
              <span class="ref-sub">知识图谱自动生成 · 只读</span>
            </div>
          </template>

          <!-- 知识库完整度横幅 -->
          <el-alert
            v-if="chapterContext"
            :type="coverageType"
            :title="chapterContext.message"
            :closable="false"
            show-icon
            class="coverage-banner"
          />

          <div v-if="!form.chapter.trim()" class="placeholder">
            <div class="placeholder-icon">📋</div>
            <div>填写章节名称后，系统自动从知识图谱计算备课参考清单</div>
          </div>

          <div v-else-if="contextLoading" class="placeholder">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <div style="margin-top: 8px">正在查询知识图谱…</div>
          </div>

          <el-collapse v-else-if="chapterContext && chapterContext.knowledge_points.length" v-model="activePanels">
            <!-- 教学顺序建议 -->
            <el-collapse-item name="order">
              <template #title>📚 教学顺序建议（按前置依赖自动排序）</template>
              <el-steps direction="vertical" :active="chapterContext.teaching_order.length">
                <el-step
                  v-for="(name, i) in chapterContext.teaching_order"
                  :key="name"
                  :title="`第 ${i + 1} 步`"
                  :description="name"
                />
              </el-steps>
            </el-collapse-item>

            <!-- 本节重难点 -->
            <el-collapse-item name="key">
              <template #title>🎯 本节重难点</template>
              <div v-if="chapterContext.key_difficult_points.length" class="tag-list">
                <el-tag
                  v-for="d in chapterContext.key_difficult_points"
                  :key="d.name"
                  type="danger"
                  effect="plain"
                >
                  {{ d.name }}（{{ d.reasons.join("、") }}）
                </el-tag>
              </div>
              <span v-else class="muted">（暂无标记）</span>
            </el-collapse-item>

            <!-- 前置预备知识 -->
            <el-collapse-item name="pre">
              <template #title>🧩 前置预备知识（递归依赖链）</template>
              <div v-if="chapterContext.prerequisite_chain.length" class="chain-list">
                <div v-for="p in chapterContext.prerequisite_chain" :key="p.id" class="chain-item">
                  <span class="chain-name" @click="openKpDetail(p)">{{ p.name }}</span>
                  <el-tag size="small" type="info" effect="plain">{{ "→".repeat(p.depth) }} 层依赖</el-tag>
                </div>
              </div>
              <span v-else class="muted">（本节无前置知识）</span>
            </el-collapse-item>

            <!-- 考纲要求 -->
            <el-collapse-item name="exam">
              <template #title>📋 考纲要求</template>
              <div class="exam-groups">
                <div v-for="kp in kpsWithExam" :key="kp.id" class="exam-group">
                  <div class="exam-kp-name">{{ kp.name }}</div>
                  <el-tag
                    v-for="e in kp.exam_points"
                    :key="e.id"
                    size="small"
                    :type="e.level === '掌握' ? 'danger' : e.level === '理解' ? 'warning' : 'info'"
                    class="exam-tag"
                  >
                    {{ e.level }} · {{ e.name }}
                  </el-tag>
                </div>
              </div>
              <span v-if="!kpsWithExam.length" class="muted">（暂无考点数据）</span>
            </el-collapse-item>

            <!-- 学生常见误区 -->
            <el-collapse-item name="mis">
              <template #title>⚠️ 学生常见误区</template>
              <div v-if="kpsWithMis.length" class="mis-list">
                <div v-for="kp in kpsWithMis" :key="kp.id" class="mis-group">
                  <div class="exam-kp-name">{{ kp.name }}</div>
                  <div v-for="m in kp.misconceptions" :key="m.id" class="mis-item">
                    <div class="mis-content">⚠️ {{ m.content }}</div>
                    <div v-if="m.correction" class="mis-correction">✅ {{ m.correction }}</div>
                  </div>
                </div>
              </div>
              <span v-if="!kpsWithMis.length" class="muted">（暂无误区数据）</span>
            </el-collapse-item>
          </el-collapse>

          <div v-else-if="chapterContext" class="placeholder">
            <div class="placeholder-icon">🔍</div>
            <div>知识库尚未收录本章节</div>
            <div class="muted">生成时将自动启用 RAG 兜底，并生成待优化工单提醒管理员补全</div>
          </div>

          <!-- 图谱共建：教师建议工单入口 -->
          <div v-if="chapterContext || form.chapter.trim()" class="contribute">
            <div class="contribute-title">📝 知识库共建（提交建议工单，管理员审核后生效）</div>
            <el-button size="small" @click="openSubmitDialog('missing')">＋ 提交缺失知识点</el-button>
            <el-button size="small" @click="openSubmitDialog('correction')">✏️ 知识点内容纠错</el-button>
            <el-button size="small" @click="openSubmitDialog('misconception')">⚠️ 新增教学误区</el-button>
            <el-button size="small" @click="openSubmitDialog('exam')">📋 补充考点</el-button>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 生成中：四步进度动画 -->
    <el-dialog v-model="generating" :show-close="false" :close-on-click-modal="false" width="420px">
      <div class="steps">
        <div v-for="(s, i) in steps" :key="i" class="step-row" :class="{ active: currentStep === i, done: currentStep > i }">
          <div class="step-icon">
            <el-icon v-if="currentStep > i"><CircleCheckFilled /></el-icon>
            <el-icon v-else-if="currentStep === i" class="is-loading"><Loading /></el-icon>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <div class="step-text">
            <div class="step-title">{{ s.title }}</div>
            <div class="step-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>
      <div class="tip">Agent 正在为您备课，请稍候…</div>
    </el-dialog>

    <!-- 共建工单提交弹窗 -->
    <el-dialog v-model="submitDialog" :title="submitDialogTitle" width="500px">
      <el-form label-width="100px">
        <template v-if="submitType === 'missing'">
          <el-form-item label="知识点名称" required>
            <el-input v-model="ticketForm.name" placeholder="如：光的折射定律" />
          </el-form-item>
          <el-form-item label="定义描述">
            <el-input v-model="ticketForm.definition" type="textarea" :rows="3" />
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="关联知识点" required>
            <el-select v-model="ticketForm.target_kp_id" placeholder="选择本清单中的知识点" style="width: 100%">
              <el-option v-for="kp in chapterContext?.knowledge_points || []" :key="kp.id" :label="kp.name" :value="kp.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="submitType === 'correction'" label="修改建议" required>
            <el-input v-model="ticketForm.suggestion" type="textarea" :rows="3" placeholder="如：该知识点的定义应改为…" />
          </el-form-item>
          <el-form-item v-if="submitType === 'misconception'" label="误区内容" required>
            <el-input v-model="ticketForm.name" placeholder="如：学生常把斜边与直角边混淆" />
          </el-form-item>
          <el-form-item v-if="submitType === 'misconception'" label="正确讲解">
            <el-input v-model="ticketForm.suggestion" placeholder="（可选）如何纠正该误区" />
          </el-form-item>
          <el-form-item v-if="submitType === 'exam'" label="考点名称" required>
            <el-input v-model="ticketForm.name" placeholder="如：利用勾股定理求边长" />
          </el-form-item>
          <el-form-item v-if="submitType === 'exam'" label="考纲层次">
            <el-radio-group v-model="ticketForm.suggestion">
              <el-radio-button value="了解">了解</el-radio-button>
              <el-radio-button value="理解">理解</el-radio-button>
              <el-radio-button value="掌握">掌握</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="submitType === 'exam'" label="考点描述">
            <el-input v-model="ticketForm.definition" type="textarea" :rows="2" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="submitDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTicket">提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { CircleCheckFilled, Loading, Upload } from "@element-plus/icons-vue"
import { adminApi, curriculumApi, documentsApi, knowledgeGraphApi, lessonPlansApi } from "@/api"
import type { KnowledgePoint } from "@/types"
import type { UploadFile } from "element-plus"

const router = useRouter()

const form = ref({
  subject: "",
  gradeLevel: "初中",
  textbookVersion: "",
  chapter: "",
  requirements: "",
})
const pickedFile = ref<File | null>(null)

const subjects = ref<{ id: string; name: string }[]>([])
const textbookVersions = ref<string[]>([])

// 章节联动：备课参考清单
const contextLoading = ref(false)
type KpWithMeta = KnowledgePoint & {
  prerequisites?: string[]
  exam_points?: { id: string; name: string; level: string; description?: string }[]
  misconceptions?: { id: string; content: string; correction?: string }[]
}
const chapterContext = ref<{
  chapter: string
  knowledge_points: KpWithMeta[]
  coverage: "complete" | "partial" | "missing"
  message: string
  teaching_order: string[]
  key_difficult_points: { name: string; reasons: string[] }[]
  prerequisite_chain: (KnowledgePoint & { depth: number })[]
} | null>(null)

const activePanels = ref(["order", "key", "pre", "exam", "mis"])
const coverageType = computed(() => {
  const c = chapterContext.value?.coverage
  return c === "complete" ? "success" : c === "partial" ? "warning" : "error"
})
const kpsWithExam = computed(() =>
  (chapterContext.value?.knowledge_points || []).filter((k) => k.exam_points?.length),
)
const kpsWithMis = computed(() =>
  (chapterContext.value?.knowledge_points || []).filter((k) => k.misconceptions?.length),
)

// 共建工单
const submitDialog = ref(false)
const submitting = ref(false)
const submitType = ref<"missing" | "correction" | "misconception" | "exam">("missing")
const ticketForm = ref({
  name: "",
  definition: "",
  suggestion: "",
  target_kp_id: "",
})
const submitDialogTitle = computed(() => {
  const map = {
    missing: "提交缺失知识点",
    correction: "知识点内容纠错",
    misconception: "新增教学误区",
    exam: "补充考点",
  }
  return map[submitType.value]
})
const KIND_MAP = {
  missing: "teacher_missing_kp",
  correction: "teacher_correction",
  misconception: "teacher_misconception",
  exam: "teacher_exam_point",
} as const

function openSubmitDialog(type: "missing" | "correction" | "misconception" | "exam") {
  submitType.value = type
  ticketForm.value = { name: "", definition: "", suggestion: type === "exam" ? "理解" : "", target_kp_id: "" }
  submitDialog.value = true
}

async function submitTicket() {
  if (submitType.value === "missing" && !ticketForm.value.name.trim()) {
    return ElMessage.warning("请填写知识点名称")
  }
  if (submitType.value !== "missing" && !ticketForm.value.target_kp_id) {
    return ElMessage.warning("请选择关联知识点")
  }
  submitting.value = true
  try {
    await adminApi.submitSuggestion({
      kind: KIND_MAP[submitType.value],
      name: ticketForm.value.name || "（未命名）",
      subject: form.value.subject || "通用",
      grade_level: form.value.gradeLevel,
      chapter: form.value.chapter || undefined,
      definition: ticketForm.value.definition || undefined,
      target_kp_id: ticketForm.value.target_kp_id || undefined,
      suggestion: ticketForm.value.suggestion || undefined,
    })
    ElMessage.success("建议工单已提交，管理员审核后生效")
    submitDialog.value = false
  } catch {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

const generating = ref(false)
const currentStep = ref(0)
const steps = [
  { title: "正在查询知识图谱", desc: "自动加载本章知识点与知识脉络" },
  { title: "检测知识库完整度", desc: "评估图谱覆盖度，决定是否启用 RAG 兜底" },
  { title: "调用 RAG 检索教材素材", desc: "从教材文本库检索章节原文与补充素材" },
  { title: "LLM 生成教案初稿并校验", desc: "固定流水线：生成 → 知识点校验报告" },
]
let stepTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  try {
    const subs = await curriculumApi.subjects()
    subjects.value = subs.data.data
    const tbs = await curriculumApi.textbooks()
    const seen = new Set<string>()
    for (const t of tbs.data.data) {
      if (t.version) seen.add(t.version)
    }
    textbookVersions.value = [...seen]
  } catch {
    // 拦截器已提示
  }
})

onBeforeUnmount(() => {
  if (stepTimer) clearInterval(stepTimer)
})

function onFileChange(f: UploadFile) {
  pickedFile.value = (f.raw as File) || null
}

async function loadChapterContext() {
  const chapter = form.value.chapter.trim()
  if (!chapter) {
    chapterContext.value = null
    return
  }
  contextLoading.value = true
  try {
    const resp = await knowledgeGraphApi.chapterContext(chapter, form.value.subject)
    chapterContext.value = resp.data as typeof chapterContext.value
  } catch {
    // 拦截器已提示
  } finally {
    contextLoading.value = false
  }
}

function openKpDetail(kp: KnowledgePoint & { depth?: number }) {
  ElMessage.info(`「${kp.name}」${kp.description ? "：" + kp.description.slice(0, 80) : ""}`)
}

async function submit() {
  if (!form.value.subject) return ElMessage.warning("请选择学科")
  if (!form.value.chapter.trim()) return ElMessage.warning("请填写单元 / 章节名称")

  generating.value = true
  currentStep.value = 0
  stepTimer = setInterval(() => {
    currentStep.value = (currentStep.value + 1) % 4
  }, 3000)

  try {
    // 自定义素材上传（后台抽取进审核队列，不阻塞教案生成）
    if (pickedFile.value) {
      await documentsApi.upload(pickedFile.value, true)
    }
    const resp = await lessonPlansApi.aiGenerate({
      knowledge_point_ids: [],
      subject: form.value.subject,
      grade_level: form.value.gradeLevel,
      extra_context: `${form.value.chapter}${form.value.textbookVersion ? `（${form.value.textbookVersion}）` : ""}`,
      style: "标准",
      requirements: form.value.requirements || "生成完整教案，含教学目标、重难点、教学过程、板书设计和课堂习题",
      summary_text: "",
      chapter: form.value.chapter,
    })
    if (stepTimer) clearInterval(stepTimer)
    generating.value = false
    ElMessage.success("教案生成完成，已附校验报告")
    router.push(`/lesson-plans/${resp.data.id}/edit`)
  } catch {
    if (stepTimer) clearInterval(stepTimer)
    generating.value = false
    // 拦截器已提示
  }
}
</script>

<style scoped>
.unified-wrap { max-width: 1280px; margin: 0 auto; padding: 8px 0 40px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; margin-bottom: 20px; }
.columns { display: flex; gap: 16px; align-items: flex-start; }
.left { flex: 1.1; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.right { flex: 0.9; min-width: 0; }
.panel { border-radius: 8px; }
.ref-head { display: flex; justify-content: space-between; align-items: center; }
.ref-sub { color: #c0c4cc; font-size: 12px; font-weight: 400; }
.upload-tip { color: #909399; font-size: 12px; margin-top: 6px; line-height: 1.7; }
.gen-row { text-align: center; }
.gen-btn { width: 100%; height: 48px; font-size: 16px; }
.coverage-banner { margin-bottom: 12px; }
.placeholder { text-align: center; color: #909399; padding: 36px 10px; }
.placeholder-icon { font-size: 36px; margin-bottom: 10px; }
.muted { color: #c0c4cc; font-size: 12px; }
.tag-list { display: flex; flex-wrap: wrap; gap: 8px; }
.chain-list { display: flex; flex-direction: column; gap: 6px; }
.chain-item { display: flex; gap: 8px; align-items: center; }
.chain-name { cursor: pointer; color: #409eff; }
.chain-name:hover { text-decoration: underline; }
.exam-groups { display: flex; flex-direction: column; gap: 10px; }
.exam-group .exam-kp-name { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
.exam-tag { margin-right: 6px; margin-bottom: 4px; }
.mis-list { display: flex; flex-direction: column; gap: 10px; }
.mis-group .exam-kp-name { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
.mis-item { background: #fef0f0; border-radius: 6px; padding: 6px 10px; margin-bottom: 6px; }
.mis-content { color: #f56c6c; font-size: 13px; }
.mis-correction { color: #67c23a; font-size: 12px; margin-top: 3px; }
.contribute { margin-top: 16px; border-top: 1px dashed #ebeef5; padding-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
.contribute-title { width: 100%; font-size: 13px; color: #606266; margin-bottom: 2px; }
.steps { display: flex; flex-direction: column; gap: 18px; margin-bottom: 12px; }
.step-row { display: flex; gap: 12px; align-items: flex-start; opacity: 0.45; transition: opacity 0.3s; }
.step-row.active { opacity: 1; }
.step-row.done { opacity: 0.8; }
.step-icon { width: 26px; height: 26px; border-radius: 50%; background: #e4e7ed; display: flex; align-items: center; justify-content: center; color: #909399; flex-shrink: 0; }
.step-row.active .step-icon { background: #409eff; color: #fff; }
.step-row.done .step-icon { background: #67c23a; color: #fff; }
.step-title { font-weight: 600; }
.step-desc { color: #909399; font-size: 12px; margin-top: 2px; }
.tip { text-align: center; color: #909399; font-size: 13px; margin-top: 10px; }
</style>
