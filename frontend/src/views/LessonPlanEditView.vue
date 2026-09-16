<template>
  <div class="edit-wrap">
    <!-- 系统提示框 -->
    <el-alert
      v-if="submittedCandidate"
      class="notice"
      type="success"
      :closable="false"
      show-icon
      title="本次备课识别到的潜在缺失知识点，已自动提交知识库审核。"
    />

    <div v-if="plan" class="columns">
      <!-- 左栏：教案内容（Markdown 渲染 / 编辑） -->
      <div class="left">
        <div class="toolbar">
          <el-input v-model="plan.title" class="title-input" placeholder="教案标题" />
          <el-button-group>
            <el-button :type="editing ? 'primary' : 'default'" @click="editing = !editing">
              {{ editing ? "预览" : "编辑" }}
            </el-button>
            <el-button type="primary" :loading="saving" @click="save">保存教案</el-button>
          </el-button-group>
        </div>

        <div v-if="editing" class="editor">
          <el-input v-model="plan.teaching_objectives" type="textarea" :rows="10" placeholder="## 教学目标" class="block" />
          <el-input v-model="plan.teaching_process" type="textarea" :rows="24" placeholder="## 教学过程（Markdown）" class="block" />
        </div>
        <div v-else class="preview markdown-body" v-html="renderedHtml" />
      </div>

      <!-- 右栏：知识点清单 + 操作 -->
      <div class="right">
        <el-card class="panel">
          <template #header>本章知识点清单</template>
          <div v-if="plan.knowledge_points.length" class="kp-list">
            <div v-for="kp in plan.knowledge_points" :key="kp.id" class="kp-item">
              <span class="kp-name" :class="{ missing: missingKps.includes(kp.name) }">{{ kp.name }}</span>
              <el-tag v-if="kp.is_key_point" size="small" :type="kp.is_key_point ? 'danger' : 'info'">
                {{ kp.is_key_point ? "核心考点" : "一般" }}
              </el-tag>
              <el-tag v-else size="small" type="info">一般</el-tag>
            </div>
          </div>
          <div v-else class="kp-empty">
            知识点来自教材文本检索
          </div>
          <el-button size="small" class="verify-btn" :loading="verifying" @click="verifyPlan">
            🔍 教案知识点校验
          </el-button>
          <el-alert
            v-if="verifyDone"
            :type="missingKps.length ? 'warning' : 'success'"
            :closable="false"
            show-icon
            class="verify-result"
            :title="missingKps.length ? `教案可能缺失 ${missingKps.length} 个知识点：${missingKps.join('、')}` : '教案已覆盖本章全部知识点 ✓'"
          />
          <!-- 固定流水线校验报告（生成时自动产出） -->
          <div v-if="plan.verification_report" class="report-box">
            <div class="report-title">
              📊 教案校验报告
              <el-tag size="small" :type="plan.verification_report.passed ? 'success' : 'warning'">
                {{ plan.verification_report.passed ? "通过" : "有改进项" }}
              </el-tag>
            </div>
            <div class="report-body">
              <template v-if="plan.verification_report.passed">教案已覆盖本章 {{ plan.verification_report.checked_count }} 个知识点的全部内容 ✓</template>
              <template v-else>
                <div v-if="plan.verification_report.missing_kps.length" class="report-item">
                  <b>缺失知识点：</b>{{ plan.verification_report.missing_kps.join("、") }}
                </div>
                <div v-if="plan.verification_report.missing_exam_points.length" class="report-item">
                  <b>未覆盖考点：</b>{{ plan.verification_report.missing_exam_points.join("、") }}
                </div>
                <div v-if="plan.verification_report.missing_prereqs.length" class="report-item">
                  <b>遗漏前置：</b>{{ plan.verification_report.missing_prereqs.join("、") }}
                </div>
                <div v-if="plan.verification_report.order_issues.length" class="report-item">
                  <b>教学顺序：</b>{{ plan.verification_report.order_issues.join("；") }}
                </div>
              </template>
            </div>
          </div>
        </el-card>

        <el-card class="panel">
          <template #header>操作</template>
          <div class="ops">
            <el-button type="primary" @click="exportWord">导出 Word</el-button>
            <el-button :loading="regenerating" @click="regenerate">重新生成</el-button>
            <el-button @click="submitDialog = true">✨ 提交缺失知识点</el-button>
          </div>
          <div class="ops-tip">
            教案中涉及但图谱缺失的知识点，可手动补充提交至管理员审核队列
          </div>
        </el-card>
      </div>
    </div>

    <!-- 教案润色助手（聊天降级为二次修改交互，嵌入编辑页底部） -->
    <el-card v-if="plan" class="polish-panel">
      <template #header>
        <div class="polish-head">
          <span>💬 教案润色助手</span>
          <span class="polish-tip">生成后的二次修改交互：如「把习题增加 2 道」「简化板书」</span>
        </div>
      </template>
      <div class="polish-messages" ref="polishRef">
        <div v-for="(m, i) in polishMessages" :key="i" class="polish-msg" :class="m.role">
          <b>{{ m.role === "user" ? "我" : "助手" }}：</b>{{ m.text }}
        </div>
        <div v-if="polishing" class="polish-msg assistant"><b>助手：</b><el-icon class="is-loading"><Loading /></el-icon></div>
      </div>
      <div class="polish-input-row">
        <el-input
          v-model="polishInput"
          placeholder="对当前教案提修改要求，如：把习题增加 2 道、简化板书…"
          :disabled="polishing"
          @keydown.enter.exact.prevent="sendPolish"
        />
        <el-button type="primary" :loading="polishing" @click="sendPolish">发送</el-button>
      </div>
    </el-card>

    <!-- 提交缺失知识点弹窗 -->
    <el-dialog v-model="submitDialog" title="提交缺失知识点" width="480px">
      <el-form label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="candForm.name" placeholder="如：光的折射定律" />
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="candForm.subject" />
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="candForm.grade_level" clearable style="width: 100%">
            <el-option v-for="g in ['小学', '初中', '高中']" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="定义">
          <el-input v-model="candForm.definition" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="前置知识点">
          <el-input v-model="candForm.prerequisites" placeholder="多个用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCandidate">提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { Loading } from "@element-plus/icons-vue"
import { marked } from "marked"
import { adminApi, authorizedFetch, lessonPlansApi, streamChat } from "@/api"
import type { LessonPlan } from "@/types"

const route = useRoute()
const router = useRouter()

const plan = ref<LessonPlan | null>(null)
const editing = ref(false)
const saving = ref(false)
const regenerating = ref(false)
const submitDialog = ref(false)
const submitting = ref(false)
const submittedCandidate = ref(false)
const candForm = ref({ name: "", subject: "", grade_level: "初中", definition: "", prerequisites: "" })

// 教案润色助手（聊天降级：仅做二次修改交互）
const polishInput = ref("")
const polishing = ref(false)
const polishMessages = ref<{ role: "user" | "assistant"; text: string }[]>([])
const polishRef = ref<HTMLElement>()

async function sendPolish() {
  const text = polishInput.value.trim()
  if (!text || polishing.value) return
  polishInput.value = ""
  polishMessages.value.push({ role: "user", text })
  polishMessages.value.push({ role: "assistant", text: "" })
  const assistant = polishMessages.value[polishMessages.value.length - 1]
  polishing.value = true
  await nextTick()
  polishRef.value?.scrollTo({ top: polishRef.value.scrollHeight })
  try {
    const history = polishMessages.value
      .slice(0, -2)
      .map((m) => ({ role: m.role, content: m.text }))
    const context = `（正在润色教案《${plan.value?.title || ""}》）${text}`
    for await (const event of streamChat(context, history)) {
      if (event.type === "token" && event.content) {
        assistant.text += event.content
        polishRef.value?.scrollTo({ top: polishRef.value.scrollHeight })
      } else if (event.type === "done" && !assistant.text) {
        assistant.text = event.reply || "（无内容）"
      } else if (event.type === "error") {
        assistant.text = assistant.text || `出错了：${event.content}`
      }
    }
  } catch {
    assistant.text = assistant.text || "请求失败，请稍后重试"
  } finally {
    polishing.value = false
  }
}

// 教案知识点校验：比对教案文本是否覆盖每个图谱知识点
const verifying = ref(false)
const verifyDone = ref(false)
const missingKps = ref<string[]>([])

function verifyPlan() {
  if (!plan.value) return
  verifying.value = true
  setTimeout(() => {
    const text = `${plan.value?.teaching_objectives || ""}\n${plan.value?.teaching_process || ""}`
    missingKps.value = (plan.value?.knowledge_points || [])
      .filter((kp) => !text.includes(kp.name))
      .map((kp) => kp.name)
    verifyDone.value = true
    verifying.value = false
  }, 300)
}

const renderedHtml = computed(() => {
  if (!plan.value) return ""
  const md = [
    `# ${plan.value.title || "教案"}`,
    `**学科**：${plan.value.subject}　**学段**：${plan.value.grade_level || "未设置"}`,
    "",
    plan.value.teaching_objectives || "",
    "",
    plan.value.teaching_process || "",
  ].join("\n")
  return marked.parse(md, { async: false }) as string
})

onMounted(async () => {
  try {
    const resp = await lessonPlansApi.get(String(route.params.id))
    plan.value = resp.data
    candForm.value.subject = resp.data.subject
    candForm.value.grade_level = resp.data.grade_level || "初中"
  } catch {
    // 拦截器已提示
  }
})

async function save() {
  if (!plan.value) return
  saving.value = true
  try {
    await lessonPlansApi.update(plan.value.id, {
      title: plan.value.title,
      teaching_objectives: plan.value.teaching_objectives,
      teaching_process: plan.value.teaching_process,
    })
    ElMessage.success("教案已保存")
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function exportWord() {
  if (!plan.value) return
  try {
    const resp = await authorizedFetch(lessonPlansApi.exportUrl(plan.value.id))
    if (resp.status === 401) return
    if (!resp.ok) throw new Error("导出失败")
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${plan.value.title}.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error("导出失败")
  }
}

async function regenerate() {
  if (!plan.value) return
  regenerating.value = true
  try {
    const resp = await lessonPlansApi.aiGenerate({
      knowledge_point_ids: plan.value.knowledge_point_ids,
      subject: plan.value.subject,
      grade_level: plan.value.grade_level || "初中",
      extra_context: "",
      style: "标准",
      requirements: "重新生成教案，优化教学设计与板书",
      summary_text: "",
    })
    ElMessage.success("已重新生成")
    router.push(`/lesson-plans/${resp.data.id}/edit`)
  } catch {
    // 拦截器已提示
  } finally {
    regenerating.value = false
  }
}

async function submitCandidate() {
  if (!candForm.value.name.trim()) return ElMessage.warning("请填写知识点名称")
  submitting.value = true
  try {
    await adminApi.submitCandidate({
      name: candForm.value.name.trim(),
      subject: candForm.value.subject || plan.value?.subject || "通用",
      grade_level: candForm.value.grade_level,
      definition: candForm.value.definition || undefined,
      prerequisites: candForm.value.prerequisites || undefined,
    })
    submittedCandidate.value = true
    submitDialog.value = false
    ElMessage.success("已提交管理员审核")
  } catch {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.edit-wrap { max-width: 1400px; margin: 0 auto; padding: 8px 0 40px; }
.notice { margin-bottom: 16px; }
.columns { display: flex; gap: 16px; align-items: flex-start; }
.left { flex: 1; min-width: 0; background: #fff; border-radius: 8px; padding: 16px; }
.right { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; gap: 16px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 14px; align-items: center; }
.title-input { flex: 1; }
.editor .block { margin-bottom: 12px; }
.preview { min-height: 400px; }
.kp-list { display: flex; flex-direction: column; gap: 8px; }
.kp-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px dashed #ebeef5; }
.kp-name { color: #606266; }
.kp-name.missing { color: #e6a23c; font-weight: 600; }
.verify-btn { width: 100%; margin-top: 12px; }
.verify-result { margin-top: 10px; }
.polish-panel { max-width: 1400px; margin: 16px auto 0; }
.polish-head { display: flex; justify-content: space-between; align-items: center; }
.polish-tip { color: #c0c4cc; font-size: 12px; font-weight: 400; }
.polish-messages { max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.polish-msg { line-height: 1.7; font-size: 13px; }
.polish-msg.user { color: #409eff; }
.polish-msg.assistant { color: #303133; background: #f5f7fa; border-radius: 6px; padding: 8px 10px; }
.polish-input-row { display: flex; gap: 10px; }
.polish-input-row .el-input { flex: 1; }
.kp-empty { color: #909399; font-size: 13px; padding: 12px 0; }
.ops { display: flex; flex-direction: column; gap: 10px; }
.ops .el-button { width: 100%; margin-left: 0; }
.ops-tip { color: #909399; font-size: 12px; margin-top: 10px; line-height: 1.6; }
.markdown-body :deep(h1) { font-size: 22px; margin: 0 0 12px; }
.markdown-body :deep(h2) { font-size: 18px; margin: 18px 0 8px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
.markdown-body :deep(h3) { font-size: 16px; margin: 14px 0 6px; }
.markdown-body :deep(p) { line-height: 1.8; margin: 6px 0; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 10px 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid #dcdfe6; padding: 6px 10px; text-align: left; }
</style>
