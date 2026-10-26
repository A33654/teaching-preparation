<template>
  <div class="wrap">
    <div v-if="hw" class="head">
      <el-input v-model="hw.title" class="title" placeholder="作业标题" :disabled="!editable" />
      <el-tag :type="hw.status === 'published' ? 'success' : 'info'" size="small">
        {{ statusText }}
      </el-tag>
      <div class="spacer" />
      <el-button :disabled="!editable" :loading="saving" @click="save">保存草稿</el-button>
      <el-button type="primary" :disabled="hw.status === 'published'" :loading="publishing" @click="publish">
        发布作业
      </el-button>
      <el-button :disabled="hw.status !== 'published'" @click="openSimulate">📥 模拟提交</el-button>
    </div>

    <el-alert
      v-if="hw && hw.status === 'published'"
      type="success"
      :closable="false"
      show-icon
      class="notice"
      title="作业已发布，已生成提交入口。本期学生提交以「模拟提交 / 教师代录」实现，落库的学号为哈希值。"
    />

    <div v-if="hw" class="columns">
      <!-- 左：题目编辑 -->
      <div class="left">
        <el-card>
          <template #header>
            <div class="card-head">
              <span>题目列表（{{ hw.questions.length }}）</span>
              <el-button size="small" type="primary" :disabled="!editable" @click="addQuestion">
                + 新增题目
              </el-button>
            </div>
          </template>

          <div v-if="!hw.questions.length" class="empty">暂无题目，点击「新增题目」添加。</div>

          <div v-for="(q, i) in hw.questions" :key="q.id" class="q-item">
            <div class="q-head">
              <b class="q-no">第 {{ i + 1 }} 题</b>
              <el-select v-model="q.type" size="small" class="q-type" :disabled="!editable">
                <el-option label="选择" value="choice" />
                <el-option label="填空" value="fill" />
                <el-option label="简答" value="short" />
                <el-option label="论述" value="essay" />
              </el-select>
              <div class="spacer" />
              <el-button size="small" type="danger" text :disabled="!editable" @click="removeQuestion(i)">
                删除
              </el-button>
            </div>

            <el-input
              v-model="q.stem"
              type="textarea"
              :rows="2"
              placeholder="题干"
              :disabled="!editable"
              class="q-stem"
            />

            <!-- 关联知识点：每题必选 ≥1 -->
            <div class="q-kp">
              <span class="label">关联知识点<span class="req">*</span></span>
              <el-select
                v-model="q.knowledge_point_ids"
                multiple
                filterable
                size="small"
                class="kp-select"
                placeholder="至少选择 1 个知识点"
                :disabled="!editable"
              >
                <el-option v-for="kp in kpPool" :key="kp.id" :label="kp.name" :value="kp.id" />
              </el-select>
              <el-tag v-if="!q.knowledge_point_ids.length" size="small" type="danger">未关联</el-tag>
            </div>

            <!-- 选择题：选项 + 正确项 -->
            <div v-if="q.type === 'choice'" class="q-body">
              <div class="label">选项</div>
              <div v-for="(_opt, oi) in q.options" :key="oi" class="opt-row">
                <el-input v-model="q.options[oi]" size="small" :disabled="!editable" :placeholder="`选项 ${String.fromCharCode(65 + oi)}`" />
                <el-button size="small" text type="danger" :disabled="!editable" @click="q.options.splice(oi, 1)">×</el-button>
              </div>
              <el-button size="small" :disabled="!editable" @click="q.options.push('')">+ 选项</el-button>
              <div class="correct-row">
                <span class="label">正确答案</span>
                <el-radio-group v-model="q.correct_option" size="small" :disabled="!editable">
                  <el-radio v-for="(_o, oi) in q.options" :key="oi" :value="oi">
                    {{ String.fromCharCode(65 + oi) }}
                  </el-radio>
                </el-radio-group>
              </div>
            </div>

            <!-- 填空题：多解 -->
            <div v-else-if="q.type === 'fill'" class="q-body">
              <div class="label">答案（可填多个，判分时任一匹配即正确）</div>
              <div v-for="(_a, ai) in q.answers" :key="ai" class="opt-row">
                <el-input v-model="q.answers[ai]" size="small" :disabled="!editable" placeholder="一个可接受答案" />
                <el-button size="small" text type="danger" :disabled="!editable" @click="q.answers.splice(ai, 1)">×</el-button>
              </div>
              <el-button size="small" :disabled="!editable" @click="q.answers.push('')">+ 答案（多解）</el-button>
            </div>

            <!-- 简答 / 论述：参考答案 -->
            <div v-else class="q-body">
              <div class="label">参考答案</div>
              <el-input
                v-model="q.reference_answer"
                type="textarea"
                :rows="2"
                :disabled="!editable"
                placeholder="参考答案 / 评分要点"
              />
            </div>
          </div>
        </el-card>
      </div>

      <!-- 右：知识点题库 -->
      <div class="right">
        <el-card>
          <template #header>知识点题库</template>
          <div class="kp-pool">
            <el-tag
              v-for="kp in kpPool"
              :key="kp.id"
              class="kp-chip"
              :type="kp.is_key_point ? 'danger' : 'info'"
              closable
              :disable-transitions="false"
              @close="removeKp(kp.id)"
            >
              {{ kp.name }}
            </el-tag>
            <div v-if="!kpPool.length" class="empty-sm">暂无知识点（从教案继承）</div>
          </div>
          <el-divider />
          <el-input v-model="kpQuery" size="small" placeholder="搜索知识点后添加" @keydown.enter="searchKp" />
          <div class="kp-results">
            <div v-for="r in kpResults" :key="r.id" class="kp-result" @click="addKp(r)">
              {{ r.name }} <span class="add">+ 添加</span>
            </div>
            <div v-if="searched && !kpResults.length" class="empty-sm">无匹配知识点</div>
          </div>
        </el-card>

        <el-card v-if="hw.lesson_plan_id">
          <template #header>来源教案</template>
          <el-button size="small" @click="gotoLessonPlan">打开来源教案</el-button>
        </el-card>

        <el-card>
          <template #header>提交记录（{{ submissions.length }}）</template>
          <div v-if="!submissions.length" class="empty-sm">暂无提交</div>
          <div v-for="s in submissions" :key="s.id" class="sub-item">
            <div class="sub-hash">
              学号哈希：{{ s.student_id_hash.slice(0, 12) }}…
              <el-tag v-if="s.superseded" size="small" type="info">
                已被后续提交覆盖
              </el-tag>
            </div>
            <div class="sub-meta">
              {{ s.status === "submitted" ? "已提交" : s.status }} ·
              {{ s.submitted_at ? new Date(s.submitted_at).toLocaleString() : "" }}
            </div>
            <div class="sub-answers">
              <div v-for="a in s.answers" :key="a.question_id" class="sub-ans">
                <b>{{ stemOf(a.question_id) }}</b> → {{ a.content }}
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 模拟提交弹窗 -->
    <el-dialog v-model="simVisible" title="模拟提交（教师代录）" width="560px">
      <el-form label-width="80px">
        <el-form-item label="学号">
          <el-input v-model="simStudentId" placeholder="如 2021001（落库为哈希）" />
        </el-form-item>
        <el-divider content-position="left">作答</el-divider>
        <el-form-item
          v-for="q in hw?.questions || []"
          :key="q.id"
          :label="`第${(hw?.questions || []).indexOf(q) + 1}题`"
        >
          <el-radio-group v-if="q.type === 'choice'" v-model="simAnswers[q.id]">
            <el-radio v-for="(o, oi) in q.options" :key="oi" :value="oi">{{ o }}</el-radio>
          </el-radio-group>
          <el-input v-else v-model="simAnswers[q.id]" :type="q.type === 'fill' ? 'text' : 'textarea'" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="simVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSimulate">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { homeworkApi, knowledgeGraphApi } from "@/api"
import type { Homework, HomeworkQuestion, KnowledgePoint, Submission } from "@/types"

const route = useRoute()
const router = useRouter()

const hw = ref<Homework | null>(null)
const saving = ref(false)
const publishing = ref(false)
const submissions = ref<Submission[]>([])

const kpQuery = ref("")
const kpResults = ref<KnowledgePoint[]>([])
const searched = ref(false)

// 模拟提交
const simVisible = ref(false)
const simStudentId = ref("")
const simAnswers = ref<Record<string, any>>({})
const submitting = ref(false)

const editable = computed(() => hw.value?.status === "draft")
const statusText = computed(() =>
  hw.value?.status === "published" ? "已发布" : hw.value?.status === "closed" ? "已关闭" : "草稿",
)
// 知识点题库：作业自身题库 + 已解析的知识点
const kpPool = computed<KnowledgePoint[]>(() => hw.value?.knowledge_points || [])

function newId() {
  return (globalThis.crypto?.randomUUID?.() as string) || String(Date.now() + Math.random())
}

function blankQuestion(): HomeworkQuestion {
  return {
    id: newId(),
    type: "short",
    stem: "",
    knowledge_point_ids: [],
    options: [],
    correct_option: null,
    answers: [],
    reference_answer: "",
  }
}

function addQuestion() {
  if (!hw.value) return
  hw.value.questions.push(blankQuestion())
}

function removeQuestion(i: number) {
  hw.value?.questions.splice(i, 1)
}

async function load() {
  const id = String(route.params.id)
  try {
    const { data } = await homeworkApi.get(id)
    hw.value = data
    await loadSubmissions()
  } catch {
    // 拦截器已提示
  }
}

async function loadSubmissions() {
  if (!hw.value) return
  try {
    const { data } = await homeworkApi.submissions(hw.value.id)
    submissions.value = data.data
  } catch {
    submissions.value = []
  }
}

async function save() {
  if (!hw.value) return
  saving.value = true
  try {
    const { data } = await homeworkApi.update(hw.value.id, {
      title: hw.value.title,
      knowledge_point_ids: hw.value.knowledge_point_ids,
      questions: hw.value.questions,
    })
    hw.value = data
    ElMessage.success("已保存")
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function publish() {
  if (!hw.value) return
  publishing.value = true
  try {
    const { data } = await homeworkApi.publish(hw.value.id)
    hw.value = data
    ElMessage.success("作业已发布，提交入口已生成")
  } catch {
    // 拦截器已提示（含知识点校验拦截）
  } finally {
    publishing.value = false
  }
}

// ============ 知识点题库 ============

async function searchKp() {
  const q = kpQuery.value.trim()
  if (!q) return
  searched.value = true
  try {
    const { data } = await knowledgeGraphApi.list({ search: q, limit: 20 })
    kpResults.value = data.data
  } catch {
    kpResults.value = []
  }
}

function addKp(kp: KnowledgePoint) {
  if (!hw.value) return
  if (!hw.value.knowledge_point_ids.includes(kp.id)) {
    hw.value.knowledge_point_ids.push(kp.id)
    hw.value.knowledge_points.push(kp)
  }
}

function removeKp(id: string) {
  if (!hw.value) return
  hw.value.knowledge_point_ids = hw.value.knowledge_point_ids.filter((x) => x !== id)
  hw.value.knowledge_points = hw.value.knowledge_points.filter((x) => x.id !== id)
  hw.value.questions.forEach((q) => {
    q.knowledge_point_ids = q.knowledge_point_ids.filter((x) => x !== id)
  })
}

// ============ 模拟提交 ============

function openSimulate() {
  simStudentId.value = ""
  simAnswers.value = {}
  simVisible.value = true
}

function stemOf(qid: string) {
  const idx = (hw.value?.questions || []).findIndex((q) => q.id === qid)
  return idx >= 0 ? `第${idx + 1}题` : qid
}

async function doSimulate() {
  if (!hw.value) return
  if (!simStudentId.value.trim()) return ElMessage.warning("请填写学号")
  submitting.value = true
  try {
    const answers = hw.value.questions.map((q) => ({
      question_id: q.id,
      content: simAnswers.value[q.id] ?? "",
    }))
    await homeworkApi.simulateSubmit(hw.value.id, {
      student_id: simStudentId.value.trim(),
      answers,
    })
    ElMessage.success("模拟提交成功（学号已哈希存储）")
    simVisible.value = false
    await loadSubmissions()
  } catch {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

function gotoLessonPlan() {
  if (hw.value?.lesson_plan_id) router.push(`/lesson-plans/${hw.value.lesson_plan_id}/edit`)
}

onMounted(load)
</script>

<style scoped>
.wrap { max-width: 1400px; margin: 0 auto; padding: 8px 0 40px; }
.head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.title { max-width: 520px; }
.spacer { flex: 1; }
.notice { margin-bottom: 12px; }
.columns { display: flex; gap: 16px; align-items: flex-start; }
.left { flex: 1; min-width: 0; }
.right { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; gap: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.q-item { border: 1px solid #ebeef5; border-radius: 8px; padding: 12px; margin-bottom: 12px; background: #fafbfc; }
.q-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.q-no { font-size: 13px; }
.q-type { width: 110px; }
.q-stem { margin-bottom: 8px; }
.q-kp { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.kp-select { flex: 1; min-width: 0; }
.label { font-size: 12px; color: #909399; }
.req { color: #f56c6c; margin-left: 2px; }
.q-body { border-top: 1px dashed #ebeef5; padding-top: 8px; }
.opt-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.opt-row .el-input { max-width: 420px; }
.correct-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.kp-pool { display: flex; flex-wrap: wrap; gap: 6px; }
.kp-chip { cursor: default; }
.kp-results { margin-top: 8px; max-height: 200px; overflow-y: auto; }
.kp-result { font-size: 13px; padding: 5px 0; border-bottom: 1px dashed #f0f0f0; cursor: pointer; color: #606266; }
.kp-result:hover { color: #409eff; }
.add { color: #409eff; font-size: 12px; }
.empty { color: #909399; text-align: center; padding: 24px 0; font-size: 13px; }
.empty-sm { color: #909399; font-size: 12px; }
.sub-item { border-bottom: 1px dashed #ebeef5; padding: 8px 0; }
.sub-hash { font-size: 12px; font-family: monospace; color: #606266; }
.sub-meta { font-size: 12px; color: #909399; margin: 2px 0; }
.sub-answers { font-size: 12px; color: #606266; }
.sub-ans { margin-top: 2px; }
</style>
