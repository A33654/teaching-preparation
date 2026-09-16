<template>
  <div class="review-wrap">
    <div class="head">
      <h1>待审核知识点队列</h1>
      <div class="subtitle">所有候选知识点在这里人工审核，审核通过才会合并进全局知识图谱</div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="load">
      <el-tab-pane label="待审核" name="pending" />
      <el-tab-pane label="已通过" name="approved" />
      <el-tab-pane label="已驳回" name="rejected" />
    </el-tabs>

    <!-- 批量操作栏 -->
    <div v-if="activeTab === 'pending'" class="batch-bar">
      <el-button size="small" @click="toggleAll">全选当前页</el-button>
      <span class="batch-count">已选 {{ selectedIds.length }} 个</span>
      <el-button size="small" type="success" :disabled="!selectedIds.length" :loading="batchLoading" @click="batchApprove">
        ✅ 批量通过（写入图谱）
      </el-button>
      <el-button size="small" type="danger" :disabled="!selectedIds.length" :loading="batchLoading" @click="batchReject">
        🗑️ 批量驳回
      </el-button>
    </div>

    <el-table
      ref="tableRef"
      :data="rows"
      border
      stripe
      v-loading="loading"
      empty-text="暂无候选知识点"
      @selection-change="onSelectionChange"
    >
      <el-table-column v-if="activeTab === 'pending'" type="selection" width="45" />
      <el-table-column prop="name" label="知识点名称" min-width="140">
        <template #default="{ row }">
          <b>{{ row.name }}</b>
        </template>
      </el-table-column>
      <el-table-column prop="subject" label="学科" width="90" />
      <el-table-column prop="grade_level" label="年级" width="80">
        <template #default="{ row }">{{ row.grade_level || "-" }}</template>
      </el-table-column>
      <el-table-column prop="textbook_version" label="教材版本" width="130">
        <template #default="{ row }">{{ row.textbook_version || "-" }}</template>
      </el-table-column>
      <el-table-column prop="definition" label="定义" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.definition || "-" }}</template>
      </el-table-column>
      <el-table-column prop="prerequisites" label="前置知识点" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ row.prerequisites || "-" }}</template>
      </el-table-column>
      <el-table-column label="工单类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="kindTag(row.kind)">{{ kindLabel(row.kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source === 'teacher_submit' ? 'warning' : 'info'">
            {{ row.source === "teacher_submit" ? "教师提交" : "LLM 抽取" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="150">
        <template #default="{ row }">{{ (row.created_at || "").replace("T", " ").slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" @click="approve(row)">✅ 通过</el-button>
            <el-button size="small" type="danger" @click="reject(row)">🗑️ 驳回</el-button>
            <el-button size="small" @click="openEdit(row)">✏️ 编辑</el-button>
          </template>
          <el-tag v-else :type="row.status === 'approved' ? 'success' : 'danger'" size="small">
            {{ row.status === "approved" ? "已写入图谱" : "已驳回" }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="editDialog" title="编辑候选知识点" width="520px">
      <el-form label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="editForm.subject" />
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="editForm.grade_level" clearable style="width: 100%">
            <el-option v-for="g in ['小学', '初中', '高中']" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="教材版本">
          <el-input v-model="editForm.textbook_version" />
        </el-form-item>
        <el-form-item label="定义">
          <el-input v-model="editForm.definition" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="前置知识点">
          <el-input v-model="editForm.prerequisites" placeholder="多个用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { adminApi } from "@/api"
import type { CandidateKp } from "@/types"

const activeTab = ref("pending")
type ReviewRow = CandidateKp & { origin?: "candidate" | "suggestion" }
const rows = ref<ReviewRow[]>([])
const loading = ref(false)
const editDialog = ref(false)
const editForm = ref<Partial<CandidateKp>>({})

function kindLabel(kind?: string | null) {
  const map: Record<string, string> = {
    llm_extraction: "LLM 抽取",
    auto_optimization: "自动优化工单",
    teacher_missing_kp: "缺失知识点",
    teacher_correction: "内容纠错",
    teacher_misconception: "教学误区",
    teacher_exam_point: "补充考点",
  }
  return map[kind || "llm_extraction"] || kind || "LLM 抽取"
}

function kindTag(kind?: string | null) {
  const map: Record<string, string> = {
    llm_extraction: "info",
    auto_optimization: "info",
    teacher_missing_kp: "primary",
    teacher_correction: "warning",
    teacher_misconception: "danger",
    teacher_exam_point: "success",
  }
  return (map[kind || "llm_extraction"] || "info") as "info" | "primary" | "warning" | "danger" | "success"
}

// 批量选择
const selectedIds = ref<string[]>([])
const batchLoading = ref(false)
const tableRef = ref<{ toggleAllSelection: () => void; clearSelection: () => void }>()

function onSelectionChange(selection: CandidateKp[]) {
  selectedIds.value = selection.map((r) => r.id)
}

function toggleAll() {
  if (selectedIds.value.length === rows.value.length) {
    tableRef.value?.clearSelection()
  } else {
    tableRef.value?.toggleAllSelection()
  }
}

async function batchApprove() {
  await ElMessageBox.confirm(
    `批量通过 ${selectedIds.value.length} 个条目并写入 Neo4j 知识图谱？`,
    "批量审核",
    { type: "success" },
  )
  batchLoading.value = true
  try {
    const selected = rows.value.filter((r) => selectedIds.value.includes(r.id))
    const candIds = selected.filter((r) => r.origin !== "suggestion").map((r) => r.id)
    const sugIds = selected.filter((r) => r.origin === "suggestion").map((r) => r.id)
    let msg = ""
    if (candIds.length) {
      const d = (await adminApi.batchApprove(candIds)).data
      msg += `LLM 候选通过 ${d.approved_count} 个`
      if (d.failed.length) msg += `，${d.failed.length} 个失败`
    }
    for (const sid of sugIds) {
      await adminApi.approveSuggestion(sid)
    }
    if (sugIds.length) msg += `${msg ? "；" : ""}教师建议通过 ${sugIds.length} 个`
    ElMessage.success(msg || "已处理")
    load()
  } catch {
    // 拦截器已提示
  } finally {
    batchLoading.value = false
  }
}

async function batchReject() {
  await ElMessageBox.confirm(
    `批量驳回 ${selectedIds.value.length} 个条目？`,
    "批量驳回",
    { type: "warning" },
  )
  batchLoading.value = true
  try {
    const selected = rows.value.filter((r) => selectedIds.value.includes(r.id))
    const candIds = selected.filter((r) => r.origin !== "suggestion").map((r) => r.id)
    const sugIds = selected.filter((r) => r.origin === "suggestion").map((r) => r.id)
    let count = 0
    if (candIds.length) {
      count += (await adminApi.batchReject(candIds)).data.rejected_count
    }
    for (const sid of sugIds) {
      await adminApi.rejectSuggestion(sid)
      count += 1
    }
    ElMessage.success(`已驳回 ${count} 个`)
    load()
  } catch {
    // 拦截器已提示
  } finally {
    batchLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    // 聚合两个数据源：LLM 批量抽取候选 + 教师共建建议工单
    const [candResp, sugResp] = await Promise.all([
      adminApi.candidates({ status: activeTab.value, limit: 200 }),
      adminApi.suggestions({ status: activeTab.value, limit: 200 }),
    ])
    const cands = candResp.data.data.map((c) => ({ ...c, origin: "candidate" as const }))
    const sugs = sugResp.data.data.map((s) => ({ ...s, origin: "suggestion" as const }))
    rows.value = [...sugs, ...cands].sort((a, b) =>
      (b.created_at || "").localeCompare(a.created_at || ""),
    )
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function approve(row: CandidateKp & { origin?: string }) {
  await ElMessageBox.confirm(`审核通过「${row.name}」并写入 Neo4j 知识图谱？`, "确认通过", { type: "success" })
  try {
    if (row.origin === "suggestion") {
      await adminApi.approveSuggestion(row.id)
    } else {
      await adminApi.approveCandidate(row.id)
    }
    ElMessage.success(`「${row.name}」已写入知识图谱`)
    load()
  } catch {
    // 拦截器已提示
  }
}

async function reject(row: CandidateKp & { origin?: string }) {
  await ElMessageBox.confirm(`驳回「${row.name}」？`, "确认驳回", { type: "warning" })
  try {
    if (row.origin === "suggestion") {
      await adminApi.rejectSuggestion(row.id)
    } else {
      await adminApi.rejectCandidate(row.id)
    }
    ElMessage.success("已驳回")
    load()
  } catch {
    // 拦截器已提示
  }
}

function openEdit(row: CandidateKp) {
  editForm.value = { ...row }
  editDialog.value = true
}

async function saveEdit() {
  if (!editForm.value.id) return
  try {
    await adminApi.editCandidate(editForm.value.id, {
      name: editForm.value.name,
      subject: editForm.value.subject,
      grade_level: editForm.value.grade_level,
      textbook_version: editForm.value.textbook_version,
      definition: editForm.value.definition,
      prerequisites: editForm.value.prerequisites,
    })
    ElMessage.success("已保存")
    editDialog.value = false
    load()
  } catch {
    // 拦截器已提示
  }
}
</script>

<style scoped>
.review-wrap { max-width: 1400px; margin: 0 auto; padding: 8px 0 40px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; margin-bottom: 10px; }
.batch-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; padding: 10px 12px; background: #f5f7fa; border-radius: 6px; }
.batch-count { color: #606266; font-size: 13px; }
</style>
