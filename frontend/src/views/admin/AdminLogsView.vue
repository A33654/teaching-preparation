<template>
  <div class="logs-wrap">
    <div class="head">
      <h1>系统日志</h1>
      <div class="subtitle">文档抽取失败记录、知识库更新记录——长 PDF 抽取失败时来这里排查</div>
    </div>

    <div class="toolbar">
      <el-button :loading="loading" @click="load">刷新</el-button>
      <span class="total">共 {{ total }} 条记录</span>
    </div>

    <el-table :data="rows" border stripe v-loading="loading" empty-text="暂无日志">
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ (row.created_at || "").replace("T", " ").slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="任务类型" width="160">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTag(row.task_type)">{{ typeLabel(row.task_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
            {{ row.status === "success" ? "成功" : row.status === "failed" ? "失败" : "信息" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="message" label="内容" min-width="420" show-overflow-tooltip />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { adminApi } from "@/api"
import type { ExtractionLogItem } from "@/types"

const rows = ref<ExtractionLogItem[]>([])
const total = ref(0)
const loading = ref(false)

function typeLabel(t: string) {
  const map: Record<string, string> = {
    document_extract: "文档抽取",
    document_upload: "文档上传",
    textbook_import: "教材导入",
    candidate_review: "知识点审核",
    candidate_submit: "教师提交",
  }
  return map[t] || t
}

function typeTag(t: string) {
  const map: Record<string, string> = {
    document_extract: "info",
    candidate_review: "success",
    candidate_submit: "warning",
  }
  return (map[t] || "info") as "success" | "info" | "warning" | "danger"
}

async function load() {
  loading.value = true
  try {
    const resp = await adminApi.logs({ limit: 200 })
    rows.value = resp.data.data
    total.value = resp.data.count
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.logs-wrap { max-width: 1200px; margin: 0 auto; padding: 8px 0 40px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; margin-bottom: 20px; }
.toolbar { display: flex; gap: 14px; align-items: center; margin-bottom: 14px; }
.total { color: #909399; font-size: 13px; }
</style>
