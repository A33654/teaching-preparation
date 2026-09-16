<template>
  <div class="kb-wrap">
    <div class="head">
      <h1>知识库管理</h1>
      <div class="subtitle">学科管理 · 图谱可视化 · 批量导入教材 PDF 构建基础图谱</div>
    </div>

    <el-row :gutter="16">
      <!-- 左：学科管理 -->
      <el-col :span="8">
        <el-card>
          <template #header>
            <div class="card-head">
              <span>学科管理</span>
              <el-button size="small" type="primary" @click="subjectDialog = true">新增学科</el-button>
            </div>
          </template>
          <el-table :data="subjects" size="small" empty-text="暂无学科">
            <el-table-column prop="name" label="学科" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="removeSubject(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="hint">
            教材版本通过「教材课标」页管理，或在批量导入时指定
          </div>
        </el-card>
      </el-col>

      <!-- 右：批量导入教材 -->
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-head">
              <span>批量导入教材 PDF（离线构建基础图谱）</span>
            </div>
          </template>
          <div class="import-row">
            <el-select v-model="importSubject" placeholder="选择学科" style="width: 160px">
              <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.name" />
              <el-option label="数学" value="数学" />
              <el-option label="物理" value="物理" />
            </el-select>
            <el-input v-model="importVersion" placeholder="教材版本（如：人教版八上）" style="width: 200px" />
            <el-upload :show-file-list="false" accept=".pdf,.docx,.txt" :before-upload="importPdf">
              <el-button type="primary" :loading="importing">上传整本教材</el-button>
            </el-upload>
          </div>
          <div class="hint">
            上传后后台自动执行：文档预处理 → 分块 → LLM 抽取 → 候选知识点进入
            <router-link to="/admin/review">待审核队列</router-link>
            （审核通过才入图）。任务进度见
            <router-link to="/admin/logs">系统日志</router-link>
            。
          </div>
          <div class="import-row">
            <el-select v-model="importSubject2" placeholder="选择学科" style="width: 160px">
              <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.name" />
              <el-option label="数学" value="数学" />
              <el-option label="物理" value="物理" />
            </el-select>
            <el-button type="success" :loading="creating" @click="createTextbook">创建教材条目</el-button>
            <span class="hint-inline">先建教材条目，再上传对应章节 PDF 进行批量抽取</span>
          </div>
        </el-card>

        <!-- 知识点考点/误区维护 -->
        <el-card class="viz-card">
          <template #header>
            <div class="card-head">
              <span>知识点考点 / 误区维护</span>
            </div>
          </template>
          <el-select
            v-model="maintainKpId"
            filterable
            placeholder="选择知识点（搜索名称）"
            style="width: 320px"
            @change="loadKpMeta"
          >
            <el-option v-for="kp in allKps" :key="kp.id" :label="kp.name" :value="kp.id" />
          </el-select>

          <div v-if="maintainKpId" class="meta-panels">
            <div class="meta-panel">
              <div class="meta-title">考点（考纲要求）</div>
              <div v-for="e in kpExams" :key="e.id" class="meta-row">
                <el-tag size="small" :type="e.level === '掌握' ? 'danger' : e.level === '理解' ? 'warning' : 'info'">{{ e.level }}</el-tag>
                <span class="meta-name">{{ e.name }}</span>
                <el-button size="small" type="danger" link @click="removeExam(e.id)">删除</el-button>
              </div>
              <div class="meta-add">
                <el-input v-model="examForm.name" placeholder="考点名称（如：利用勾股定理求边长）" size="small" />
                <el-select v-model="examForm.level" size="small" style="width: 90px">
                  <el-option v-for="l in ['了解', '理解', '掌握']" :key="l" :label="l" :value="l" />
                </el-select>
                <el-button size="small" type="primary" @click="addExam">添加</el-button>
              </div>
            </div>
            <div class="meta-panel">
              <div class="meta-title">误区 / 易错点</div>
              <div v-for="m in kpMiss" :key="m.id" class="meta-row">
                <span class="meta-name">⚠️ {{ m.content }}</span>
                <el-button size="small" type="danger" link @click="removeMis(m.id)">删除</el-button>
              </div>
              <div class="meta-add">
                <el-input v-model="misForm.content" placeholder="误区内容（如：误把斜边当成直角边）" size="small" />
                <el-input v-model="misForm.correction" placeholder="纠正（可选）" size="small" />
                <el-button size="small" type="primary" @click="addMis">添加</el-button>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 图谱可视化（简易版） -->
        <el-card class="viz-card">
          <template #header>
            <div class="card-head">
              <span>知识图谱可视化</span>
              <el-button size="small" @click="loadGraph">刷新</el-button>
            </div>
          </template>
          <div v-if="graphNodes.length" class="viz-box">
            <svg :viewBox="`0 0 ${W} ${H}`" width="100%">
              <line
                v-for="(e, i) in edges"
                :key="'e' + i"
                :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
                stroke="#c0c4cc" stroke-width="1.2"
              />
              <g v-for="(n, i) in graphNodes" :key="n.id">
                <circle :cx="n.x" :cy="n.y" :r="nodeRadius(n)" :fill="n.is_key_point ? '#f56c6c' : '#409eff'" :opacity="0.85" />
                <text :x="n.x" :y="n.y + 3" text-anchor="middle" font-size="11" fill="#fff" font-weight="600">{{ n.label }}</text>
              </g>
            </svg>
          </div>
          <el-empty v-else description="暂无图谱数据，先去审核通过一些候选知识点" :image-size="70" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="subjectDialog" title="新增学科" width="400px">
      <el-form>
        <el-form-item label="名称" required>
          <el-input v-model="newSubject.name" placeholder="如：物理" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newSubject.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subjectDialog = false">取消</el-button>
        <el-button type="primary" @click="addSubject">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { adminApi, curriculumApi, documentsApi, knowledgeGraphApi } from "@/api"
import type { GraphData, KnowledgePoint, Subject } from "@/types"

const subjects = ref<Subject[]>([])
const subjectDialog = ref(false)
const newSubject = ref({ name: "", description: "" })
const importSubject = ref("")
const importSubject2 = ref("")
const importVersion = ref("")
const importing = ref(false)
const creating = ref(false)

const graphNodes = ref<{ id: string; label: string; x: number; y: number; is_key_point?: boolean }[]>([])
const edges = ref<{ x1: number; y1: number; x2: number; y2: number }[]>([])
const W = 700
const H = 420

// 考点/误区维护
const allKps = ref<KnowledgePoint[]>([])
const maintainKpId = ref("")
const kpExams = ref<{ id: string; name: string; level: string; description?: string }[]>([])
const kpMiss = ref<{ id: string; content: string; correction?: string }[]>([])
const examForm = ref({ name: "", level: "理解" })
const misForm = ref({ content: "", correction: "" })

async function loadAllKps() {
  try {
    const resp = await knowledgeGraphApi.list({ limit: 500 })
    allKps.value = resp.data.data
  } catch {
    // 拦截器已提示
  }
}

async function loadKpMeta() {
  if (!maintainKpId.value) return
  try {
    const [e, m] = await Promise.all([
      knowledgeGraphApi.examPoints(maintainKpId.value),
      knowledgeGraphApi.misconceptions(maintainKpId.value),
    ])
    kpExams.value = e.data.data
    kpMiss.value = m.data.data
  } catch {
    // 拦截器已提示
  }
}

async function addExam() {
  if (!examForm.value.name.trim()) return ElMessage.warning("请填写考点名称")
  try {
    await knowledgeGraphApi.addExamPoint(maintainKpId.value, {
      name: examForm.value.name.trim(),
      level: examForm.value.level,
    })
    examForm.value.name = ""
    loadKpMeta()
  } catch {
    // 拦截器已提示
  }
}

async function removeExam(examId: string) {
  try {
    await knowledgeGraphApi.deleteExamPoint(maintainKpId.value, examId)
    loadKpMeta()
  } catch {
    // 拦截器已提示
  }
}

async function addMis() {
  if (!misForm.value.content.trim()) return ElMessage.warning("请填写误区内容")
  try {
    await knowledgeGraphApi.addMisconception(maintainKpId.value, {
      content: misForm.value.content.trim(),
      correction: misForm.value.correction || undefined,
    })
    misForm.value = { content: "", correction: "" }
    loadKpMeta()
  } catch {
    // 拦截器已提示
  }
}

async function removeMis(misId: string) {
  try {
    await knowledgeGraphApi.deleteMisconception(maintainKpId.value, misId)
    loadKpMeta()
  } catch {
    // 拦截器已提示
  }
}

function nodeRadius(n: { is_key_point?: boolean }) {
  return n.is_key_point ? 15 : 10
}

async function load() {
  try {
    const resp = await curriculumApi.subjects()
    subjects.value = resp.data.data
  } catch {
    // 拦截器已提示
  }
}

onMounted(() => {
  load()
  loadGraph()
  loadAllKps()
})

async function addSubject() {
  if (!newSubject.value.name.trim()) return ElMessage.warning("请填写学科名称")
  try {
    await curriculumApi.createSubject({ name: newSubject.value.name, description: newSubject.value.description || null })
    ElMessage.success("学科已创建")
    subjectDialog.value = false
    newSubject.value = { name: "", description: "" }
    load()
  } catch {
    // 拦截器已提示
  }
}

async function removeSubject(row: Subject) {
  await ElMessageBox.confirm(`删除学科「${row.name}」？`, "确认删除", { type: "warning" })
  try {
    await curriculumApi.deleteSubject(row.id)
    ElMessage.success("已删除")
    load()
  } catch {
    // 拦截器已提示
  }
}

async function createTextbook() {
  if (!importSubject2.value) return ElMessage.warning("请选择学科")
  if (!importVersion.value.trim()) return ElMessage.warning("请填写教材版本")
  creating.value = true
  try {
    const sub = subjects.value.find((s) => s.name === importSubject2.value)
    if (!sub) return ElMessage.warning("请先创建该学科")
    await curriculumApi.createTextbook({
      name: `${importSubject2.value}教材`,
      version: importVersion.value,
      grade_level: "初中",
      subject_id: sub.id,
    })
    ElMessage.success("教材条目已创建")
  } catch {
    // 拦截器已提示
  } finally {
    creating.value = false
  }
}

async function importPdf(file: File) {
  if (!importSubject.value) return ElMessage.warning("请先选择学科")
  importing.value = true
  try {
    await documentsApi.upload(file, true)
    ElMessage.success("教材已上传，后台正在离线批量抽取（抽取结果进入待审核队列）")
  } catch {
    // 拦截器已提示
  } finally {
    importing.value = false
  }
  return false
}

async function loadGraph() {
  try {
    const resp = await knowledgeGraphApi.fullGraph()
    const g: GraphData = resp.data
    const nodes = (g.nodes || []).slice(0, 60)
    const nodeIds = new Set(nodes.map((n) => n.id))
    const links = (g.edges || []).filter(
      (e) => nodeIds.has(e.source_id) && nodeIds.has(e.target_id),
    )
    // 圆形布局
    const cx = W / 2
    const cy = H / 2
    const r = Math.min(W, H) / 2 - 60
    const positioned = nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2
      return {
        id: n.id,
        label: (n.name || n.id).slice(0, 6),
        is_key_point: !!n.is_key_point,
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
      }
    })
    const pos = new Map(positioned.map((n) => [n.id, n]))
    graphNodes.value = positioned
    edges.value = links
      .map((e) => {
        const a = pos.get(e.source_id)
        const b = pos.get(e.target_id)
        if (!a || !b) return null
        return { x1: a.x, y1: a.y, x2: b.x, y2: b.y }
      })
      .filter(Boolean) as typeof edges.value
  } catch {
    // 拦截器已提示
  }
}
</script>

<style scoped>
.kb-wrap { max-width: 1400px; margin: 0 auto; padding: 8px 0 40px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; margin-bottom: 20px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.hint { color: #909399; font-size: 12px; margin-top: 12px; line-height: 1.7; }
.hint-inline { color: #909399; font-size: 12px; }
.import-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.viz-card { margin-top: 16px; }
.viz-box { border: 1px solid #ebeef5; border-radius: 6px; padding: 8px; }
.meta-panels { display: flex; gap: 16px; margin-top: 14px; }
.meta-panel { flex: 1; border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px; }
.meta-title { font-weight: 600; margin-bottom: 8px; }
.meta-row { display: flex; gap: 6px; align-items: center; padding: 4px 0; }
.meta-name { flex: 1; font-size: 13px; color: #303133; }
.meta-add { display: flex; gap: 6px; margin-top: 8px; align-items: center; }
</style>
