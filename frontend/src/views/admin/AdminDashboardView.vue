<template>
  <div class="admin-wrap">
    <h1>管理员工作台</h1>
    <div class="subtitle">知识库维护中心：候选知识点审核 → 增量图谱补全</div>

    <el-row :gutter="16" class="stats">
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="stat-card clickable" @click="$router.push('/admin/review')">
          <div class="stat-num">{{ stats.pending_candidates }}</div>
          <div class="stat-label">待审核知识点</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-num">{{ stats.subjects_count }}</div>
          <div class="stat-label">学科数量</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="stat-card clickable" @click="$router.push('/knowledge-graph')">
          <div class="stat-num">{{ stats.knowledge_points_count }}</div>
          <div class="stat-label">图谱知识点总数</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-num">
            {{ stats.documents_total }}
            <span class="stat-sub">
              （处理中 {{ stats.documents_processing }} / 失败 {{ stats.documents_failed }}）
            </span>
          </div>
          <div class="stat-label">文档处理任务</div>
        </el-card>
      </el-col>
    </el-row>

    <div class="quick">
      <el-card shadow="hover" class="q-item" @click="$router.push('/admin/review')">
        <div class="q-icon">✅</div>
        <div>待审核知识点队列</div>
        <div class="q-desc">审核 LLM / 教师提交的候选知识点，通过后写入 Neo4j</div>
      </el-card>
      <el-card shadow="hover" class="q-item" @click="$router.push('/admin/knowledge')">
        <div class="q-icon">📚</div>
        <div>知识库管理</div>
        <div class="q-desc">学科管理、图谱可视化、批量导入教材 PDF</div>
      </el-card>
      <el-card shadow="hover" class="q-item" @click="$router.push('/admin/logs')">
        <div class="q-icon">📋</div>
        <div>系统日志</div>
        <div class="q-desc">查看文档抽取失败记录与知识库更新记录</div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { adminApi } from "@/api"

const stats = ref({
  pending_candidates: 0,
  subjects_count: 0,
  knowledge_points_count: 0,
  documents_total: 0,
  documents_processing: 0,
  documents_failed: 0,
})

onMounted(async () => {
  try {
    const resp = await adminApi.stats()
    stats.value = resp.data
  } catch {
    // 拦截器已提示
  }
})
</script>

<style scoped>
.admin-wrap { max-width: 1200px; margin: 0 auto; padding: 8px 0 40px; }
.admin-wrap h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; margin-bottom: 24px; }
.stats { margin-bottom: 28px; }
.stat-card { text-align: center; padding: 8px 0; }
.clickable { cursor: pointer; }
.stat-num { font-size: 32px; font-weight: 700; color: #409eff; }
.stat-sub { font-size: 12px; color: #909399; font-weight: 400; }
.stat-label { color: #606266; margin-top: 6px; }
.quick { display: flex; gap: 16px; flex-wrap: wrap; }
.q-item { flex: 1; min-width: 220px; cursor: pointer; text-align: center; }
.q-icon { font-size: 30px; margin-bottom: 8px; }
.q-desc { color: #909399; font-size: 12px; margin-top: 8px; line-height: 1.6; }
</style>
