<template>
  <div>
    <div class="page-header">
      <div>
        <h1>文档管理</h1>
        <div class="subtitle">上传教材文档，LangGraph 自动抽取知识点写入 Neo4j 知识图谱</div>
      </div>
      <el-upload
        :show-file-list="false"
        :http-request="handleUpload"
        accept=".pdf,.docx,.txt"
        :disabled="uploading"
      >
        <el-button type="primary" :loading="uploading" :icon="Upload">
          {{ uploading ? "上传解析中..." : "上传文档" }}
        </el-button>
      </el-upload>
    </div>

    <div class="card-panel">
      <div class="toolbar">
        <el-input
          v-model="search"
          placeholder="搜索文档内知识点 / 内容..."
          clearable
          style="width: 320px"
          :prefix-icon="Search"
          @keyup.enter="doSearch"
        />
        <el-button type="primary" plain :icon="Search" @click="doSearch">搜索</el-button>
      </div>

      <!-- 搜索结果 -->
      <div v-if="searchResult" class="search-result">
        <el-alert
          :title="`「${searchResult.query}」的检索结果：${searchResult.knowledge_points.length} 个知识点、${searchResult.documents.length} 篇文档`"
          type="success"
          :closable="false"
        />
        <div v-if="searchResult.knowledge_points.length" class="result-section">
          <h4>知识图谱节点</h4>
          <el-tag
            v-for="kp in searchResult.knowledge_points"
            :key="kp.id"
            type="warning"
            effect="plain"
            class="result-tag"
          >
            {{ kp.name }}
            <span class="tag-sub">（{{ kp.subject }}）</span>
          </el-tag>
        </div>
        <div v-if="searchResult.documents.length" class="result-section">
          <h4>文档内容</h4>
          <div v-for="d in searchResult.documents" :key="d.id" class="doc-hit">
            <b>{{ d.filename }}</b>
            <p>{{ d.snippet }}</p>
          </div>
        </div>
        <el-button size="small" text @click="searchResult = null">收起结果</el-button>
      </div>

      <el-table v-loading="loading" :data="docs" stripe>
        <el-table-column prop="original_filename" label="文件名" min-width="220">
          <template #default="{ row }">
            <el-icon :size="16" style="vertical-align: -3px"><Document /></el-icon>
            <span style="margin-left: 6px">{{ row.original_filename }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.file_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="学科" width="100">
          <template #default="{ row }">
            {{ subjectName(row.subject_id) || "—" }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="候选知识点" width="120">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.knowledge_points.length"
              :content="row.knowledge_points.map((k: any) => k.name).join('、')"
            >
              <el-tag size="small" type="warning" effect="plain">
                {{ row.knowledge_points.length }} 个
              </el-tag>
            </el-tooltip>
            <span v-else class="muted">待审核队列</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="previewFile(row)">预览</el-button>
            <el-button size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :loading="analyzingId === row.id"
              @click="analyze(row)"
            >
              重新抽取
            </el-button>
            <el-popconfirm title="确定删除该文档？" @confirm="remove(row)">
              <template #reference>
                <el-button size="small" type="danger" plain>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detailDoc?.original_filename" size="45%">
      <template v-if="detailDoc">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusType(detailDoc.status)">
              {{ statusLabel(detailDoc.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="大小">{{ formatSize(detailDoc.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="上传时间">{{ formatTime(detailDoc.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="关联知识点">{{ detailDoc.knowledge_points.length }} 个</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">文档概括（LangGraph 抽取）</h4>
        <el-alert
          v-if="detailDoc.summary"
          :title="detailDoc.summary"
          type="success"
          :closable="false"
          show-icon
        />

        <h4 class="section-title">关联知识点</h4>
        <div v-if="detailDoc.knowledge_points.length" class="kp-list">
          <el-tag
            v-for="kp in detailDoc.knowledge_points"
            :key="kp.id"
            type="warning"
            effect="plain"
            class="result-tag"
            @click="router.push('/knowledge-graph')"
          >
            {{ kp.name }}
            <span class="tag-sub">（{{ kp.subject }}{{ kp.is_key_point ? " · 核心考点" : "" }}）</span>
          </el-tag>
        </div>
        <el-empty v-else description="尚未抽取知识点，请点击「重新抽取」" :image-size="60" />

        <h4 class="section-title">文本预览</h4>
        <div class="text-preview">{{ (detailDoc.extracted_text || "").slice(0, 2000) }}</div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { Document, Search, Upload } from "@element-plus/icons-vue"
import { authorizedFetch, curriculumApi, documentsApi } from "@/api"
import type { DocumentItem } from "@/types"

const router = useRouter()
const subjectsMap = ref<Record<string, string>>({})

function subjectName(id: string | null): string {
  return id ? subjectsMap.value[id] || "" : ""
}

async function loadSubjects() {
  try {
    const resp = await curriculumApi.subjects()
    const map: Record<string, string> = {}
    for (const s of resp.data.data) map[s.id] = s.name
    subjectsMap.value = map
  } catch {
    // 拦截器已提示
  }
}

async function previewFile(row: DocumentItem) {
  try {
    const resp = await authorizedFetch(`/api/v1/documents/${row.id}/file`)
    if (resp.status === 401) return
    if (!resp.ok) {
      ElMessage.error("文件预览失败")
      return
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    window.open(url, "_blank")
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch {
    ElMessage.error("文件预览失败")
  }
}
const docs = ref<DocumentItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const analyzingId = ref("")
const search = ref("")
const searchResult = ref<{
  query: string
  knowledge_points: { id: string; name: string; subject: string }[]
  documents: { id: string; filename: string; snippet: string }[]
} | null>(null)
const detailVisible = ref(false)
const detailDoc = ref<DocumentItem | null>(null)

async function load() {
  loading.value = true
  try {
    const resp = await documentsApi.list({ limit: 100 })
    docs.value = resp.data.data
  } finally {
    loading.value = false
  }
}

async function handleUpload({ file }: { file: File }) {
  uploading.value = true
  try {
    const resp = await documentsApi.upload(file, true)
    const docId = resp.data.id
    ElMessage.success("上传成功，正在后台抽取知识点...")
    // 抽取在后台执行：每 3s 刷新列表，直到该文档结束（completed/failed，最长约 2 分钟）
    for (let i = 0; i < 40; i++) {
      await new Promise((resolve) => setTimeout(resolve, 3000))
      await load()
      const doc = docs.value.find((d) => d.id === docId)
      if (!doc) break
      if (doc.status === "completed") {
        ElMessage.success("知识抽取完成，已写入知识图谱")
        break
      }
      if (doc.status === "failed") {
        ElMessage.error(doc.error_message || "知识抽取失败")
        break
      }
    }
  } catch {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

async function analyze(row: DocumentItem) {
  analyzingId.value = row.id
  try {
    const resp = await documentsApi.analyze(row.id)
    ElMessage.success(
      `抽取完成：${resp.data.extraction.knowledge_points_count} 个知识点、${resp.data.extraction.relations_count} 条关系`,
    )
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    analyzingId.value = ""
  }
}

async function remove(row: DocumentItem) {
  await documentsApi.remove(row.id)
  ElMessage.success("已删除")
  load()
}

async function doSearch() {
  const q = search.value.trim()
  if (!q) return
  const resp = await documentsApi.search(q)
  searchResult.value = resp.data
}

function openDetail(row: DocumentItem) {
  detailDoc.value = row
  detailVisible.value = true
}

function formatSize(bytes: number): string {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function formatTime(t?: string | null): string {
  if (!t) return "—"
  return new Date(t).toLocaleString("zh-CN", { hour12: false })
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    uploaded: "已上传",
    parsing: "解析中",
    analyzing: "抽取中",
    completed: "已完成",
    failed: "失败",
  }
  return map[s] || s
}

function statusType(s: string): "success" | "warning" | "danger" | "info" {
  if (s === "completed") return "success"
  if (s === "failed") return "danger"
  if (s === "analyzing" || s === "parsing") return "warning"
  return "info"
}

onMounted(() => {
  load()
  loadSubjects()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.search-result {
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
  background: #f0f9eb;
}

.result-section {
  margin-top: 10px;
}

.result-section h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #606266;
}

.result-tag {
  margin: 0 6px 6px 0;
}

.tag-sub {
  color: #b88230;
  font-size: 11px;
}

.doc-hit {
  padding: 8px;
  margin-bottom: 8px;
  background: #fff;
  border-radius: 6px;
  font-size: 13px;
}

.doc-hit p {
  margin: 4px 0 0;
  color: #606266;
}

.muted {
  color: #c0c4cc;
}

.section-title {
  margin: 18px 0 10px;
  font-size: 14px;
  color: #303133;
}

.kp-list {
  display: flex;
  flex-wrap: wrap;
}

.text-preview {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
}
</style>
