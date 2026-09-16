<template>
  <div>
    <div class="page-header">
      <div>
        <h1>PPT 生成</h1>
        <div class="subtitle">上传文档 → LangGraph PPT 大纲图生成内容 → 自动渲染 PPTX 下载</div>
      </div>
    </div>

    <!-- 生成区 -->
    <div class="card-panel gen-panel">
      <el-upload
        drag
        :show-file-list="false"
        :http-request="handleGenerate"
        accept=".pdf,.docx,.txt"
        :disabled="generating"
      >
        <el-icon class="el-icon--upload" :size="48"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文档拖到此处，或 <em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF / DOCX / TXT，AI 将根据文档内容生成教学 PPT</div>
        </template>
      </el-upload>

      <div class="gen-options">
        <el-form inline>
          <el-form-item label="风格">
            <el-select v-model="style" style="width: 150px">
              <el-option label="专业" value="professional" />
              <el-option label="简约" value="minimal" />
              <el-option label="活泼" value="vivid" />
            </el-select>
          </el-form-item>
          <el-form-item label="页数">
            <el-input-number v-model="slideCount" :min="4" :max="20" />
          </el-form-item>
        </el-form>
        <el-button v-if="generating" type="primary" loading>AI 生成中...</el-button>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="card-panel">
      <h3 class="panel-title">生成历史</h3>
      <el-table v-loading="loading" :data="records" stripe>
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column prop="original_filename" label="源文档" min-width="180" />
        <el-table-column label="页数" width="90">
          <template #default="{ row }">{{ row.slide_count }} 页</template>
        </el-table-column>
        <el-table-column label="风格" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ styleLabel(row.style) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="生成时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain :icon="Download" @click="downloadPpt(row)">
              下载 PPTX
            </el-button>
            <el-button size="small" :icon="Edit" @click="openEditor(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editorVisible" title="编辑 PPT 内容" width="720px" top="4vh">
      <div class="editor-list">
        <div v-for="(slide, i) in editingSlides" :key="i" class="slide-editor">
          <div class="slide-head">
            <b>第 {{ i + 1 }} 页</b>
            <el-button size="small" text type="danger" @click="editingSlides.splice(i, 1)">删除</el-button>
          </div>
          <el-input v-model="slide.title" placeholder="页面标题" />
          <div class="bullet-list">
            <div v-for="(b, bi) in slide.bullets" :key="bi" class="bullet-row">
              <el-input v-model="slide.bullets[bi]" size="small" placeholder="要点内容" />
              <el-button size="small" text type="danger" @click="slide.bullets.splice(bi, 1)">✕</el-button>
            </div>
            <el-button size="small" text type="primary" @click="slide.bullets.push('')">+ 添加要点</el-button>
          </div>
        </div>
        <el-button :icon="Plus" @click="editingSlides.push({ title: '新页面', bullets: [''] })">
          添加页面
        </el-button>
      </div>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePpt">保存并重新生成 PPTX</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { Delete, Download, Edit, Plus, UploadFilled } from "@element-plus/icons-vue"
import { authorizedFetch, summarizeApi } from "@/api"
import type { PptRecord, SlideContent } from "@/types"

const style = ref("professional")
const slideCount = ref(8)
const generating = ref(false)
const records = ref<PptRecord[]>([])
const loading = ref(false)
const editingRecord = ref<PptRecord | null>(null)

const editorVisible = ref(false)
const saving = ref(false)
const editingSlides = ref<SlideContent[]>([])

async function load() {
  loading.value = true
  try {
    const resp = await summarizeApi.pptList()
    records.value = resp.data.data
  } finally {
    loading.value = false
  }
}

async function handleGenerate({ file }: { file: File }) {
  generating.value = true
  try {
    const resp = await summarizeApi.generatePpt(file, style.value, slideCount.value)
    const blob = resp.data
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${(file.name || "presentation").split(".")[0]}.pptx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success("PPT 生成成功，已开始下载")
    setTimeout(load, 1500)
  } catch {
    // 拦截器已提示
  } finally {
    generating.value = false
  }
}

function downloadPpt(row: PptRecord) {
  authorizedFetch(summarizeApi.pptExportUrl(row.id))
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
      a.download = `${row.title}.pptx`
      a.click()
      URL.revokeObjectURL(url)
    })
    .catch(() => ElMessage.error("导出失败"))
}

function openEditor(row: PptRecord) {
  editingRecord.value = row
  try {
    editingSlides.value = row.slides_json ? JSON.parse(row.slides_json) : []
  } catch {
    editingSlides.value = []
  }
  editorVisible.value = true
}

async function savePpt() {
  if (!editingRecord.value) return
  saving.value = true
  try {
    const resp = await summarizeApi.savePpt(
      editingRecord.value.id,
      editingSlides.value.filter((s) => s.title.trim()),
      style.value,
    )
    const blob = resp.data
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${editingRecord.value.title}.pptx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success("已保存并重新生成")
    editorVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

function styleLabel(s?: string | null): string {
  const map: Record<string, string> = {
    professional: "专业",
    minimal: "简约",
    vivid: "活泼",
  }
  return map[s || ""] || s || "—"
}

function formatTime(t?: string | null): string {
  if (!t) return "—"
  return new Date(t).toLocaleString("zh-CN", { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.gen-panel {
  margin-bottom: 16px;
}

.gen-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
}

.panel-title {
  margin: 0 0 14px;
  font-size: 15px;
}

.slide-editor {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: #fafafa;
}

.slide-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.bullet-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bullet-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.editor-list {
  max-height: 60vh;
  overflow-y: auto;
}
</style>
