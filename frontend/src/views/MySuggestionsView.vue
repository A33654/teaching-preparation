<template>
  <div class="mine-wrap">
    <div class="head">
      <h1>我的共建</h1>
      <div class="subtitle">提交的知识库共建建议工单及审核进度回推，管理员审核结果会在这里展示</div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="load">
      <el-tab-pane label="全部" name="" />
      <el-tab-pane label="待审核" name="pending" />
      <el-tab-pane label="已通过" name="approved" />
      <el-tab-pane label="已驳回" name="rejected" />
    </el-tabs>

    <el-table
      :data="rows"
      v-loading="loading"
      border
      stripe
      empty-text="暂无共建建议工单"
    >
      <el-table-column prop="name" label="建议内容" min-width="160">
        <template #default="{ row }"><b>{{ row.name }}</b></template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="kindTag(row.kind)">{{ kindLabel(row.kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="subject" label="学科" width="90" />
      <el-table-column prop="chapter" label="章节" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.chapter || "-" }}</template>
      </el-table-column>
      <el-table-column label="提交时间" width="160">
        <template #default="{ row }">{{ (row.created_at || "").replace("T", " ").slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="驳回理由" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.status === 'rejected' && row.review_note" class="reject-note">{{ row.review_note }}</span>
          <span v-else-if="row.status === 'rejected'" class="muted">（未填写理由）</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { adminApi } from "@/api"
import type { CandidateKp } from "@/types"

const activeTab = ref("")
const rows = ref<CandidateKp[]>([])
const loading = ref(false)

function kindLabel(kind?: string | null) {
  const map: Record<string, string> = {
    missing_kp: "缺失知识点",
    correction: "内容纠错",
    misconception: "教学误区",
    exam_point: "补充考点",
  }
  return map[kind || ""] || kind || "其他"
}

function kindTag(kind?: string | null) {
  const map: Record<string, string> = {
    missing_kp: "primary",
    correction: "warning",
    misconception: "danger",
    exam_point: "success",
  }
  return (map[kind || ""] || "info") as "info" | "primary" | "warning" | "danger" | "success"
}

function statusLabel(s?: string) {
  return s === "approved" ? "已通过" : s === "rejected" ? "已驳回" : "待审核"
}

function statusTag(s?: string) {
  return s === "approved" ? "success" : s === "rejected" ? "danger" : "warning"
}

async function load() {
  loading.value = true
  try {
    const resp = await adminApi.suggestionsMine({ status: activeTab.value, limit: 200 })
    rows.value = resp.data.data
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mine-wrap { max-width: 1200px; margin: 0 auto; padding: 8px 0 40px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; margin-bottom: 12px; }
.reject-note { color: #f56c6c; }
.muted { color: #c0c4cc; }
</style>
