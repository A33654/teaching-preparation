<template>
  <div class="dash-wrap">
    <!-- 系统提示横幅 -->
    <el-alert
      class="banner"
      type="warning"
      :closable="false"
      show-icon
      title="当前章节知识库尚不完整，生成教案将启用 RAG 兜底"
    />

    <div class="hero">
      <div>
        <h1>工作台</h1>
        <div class="subtitle">
          当前知识库：{{ kpCount }} 个知识点 · 学科 {{ subjectList.length }} 个
        </div>
      </div>
      <el-button type="primary" size="large" :icon="Plus" @click="$router.push('/new-lesson')">
        新建备课任务
      </el-button>
    </div>

    <!-- 备课项目列表 -->
    <div class="section-title">
      <h3>我的备课项目</h3>
      <el-button text type="primary" @click="$router.push('/lesson-plans')">全部教案 →</el-button>
    </div>
    <el-row v-if="plans.length" :gutter="16">
      <el-col v-for="p in plans" :key="p.id" :xs="24" :sm="12" :md="8" :lg="6" class="col">
        <el-card class="plan-card" shadow="hover" @click="$router.push(`/lesson-plans/${p.id}/edit`)">
          <div class="plan-title">{{ p.title || "未命名教案" }}</div>
          <div class="plan-meta">
            <el-tag size="small">{{ p.subject }}</el-tag>
            <el-tag size="small" type="info">{{ p.grade_level || "未设置学段" }}</el-tag>
            <el-tag size="small" :type="p.knowledge_point_ids.length ? 'success' : 'warning'">
              {{ p.knowledge_point_ids.length ? "已完成" : "草稿" }}
            </el-tag>
          </div>
          <div class="plan-time">{{ (p.created_at || "").slice(0, 10) }} 创建</div>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-else description="还没有备课项目，点击右上角「新建备课任务」开始" />

    <!-- 快捷操作 -->
    <div class="section-title"><h3>快捷操作</h3></div>
    <div class="quick-actions">
      <el-card shadow="hover" class="qa-card" @click="$router.push('/documents')">
        <div class="qa-icon">📁</div>
        <div>我的素材库</div>
        <div class="qa-desc">管理上传的补充 PDF 素材</div>
      </el-card>
      <el-card shadow="hover" class="qa-card" @click="$router.push('/lesson-plans')">
        <div class="qa-icon">✍️</div>
        <div>教案编辑与润色</div>
        <div class="qa-desc">编辑教案，底部 AI 助手迭代润色</div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Plus } from "@element-plus/icons-vue"
import { knowledgeGraphApi, curriculumApi, lessonPlansApi } from "@/api"
import type { LessonPlan } from "@/types"

const plans = ref<LessonPlan[]>([])
const kpCount = ref(0)
const subjectList = ref<{ id: string; name: string }[]>([])

onMounted(async () => {
  try {
    const [lp, kps, subs] = await Promise.all([
      lessonPlansApi.list({ limit: 8 }),
      knowledgeGraphApi.list({ limit: 1 }),
      curriculumApi.subjects(),
    ])
    plans.value = lp.data.data
    kpCount.value = kps.data.count
    subjectList.value = subs.data.data
  } catch {
    // 拦截器已提示
  }
})
</script>

<style scoped>
.dash-wrap { max-width: 1200px; margin: 0 auto; padding: 8px 0 40px; }
.banner { margin-bottom: 20px; }
.hero { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.hero h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #909399; font-size: 14px; }
.section-title { display: flex; justify-content: space-between; align-items: center; margin: 28px 0 14px; }
.section-title h3 { margin: 0; }
.col { margin-bottom: 16px; }
.plan-card { cursor: pointer; }
.plan-title { font-size: 15px; font-weight: 600; margin-bottom: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plan-meta { display: flex; gap: 6px; margin-bottom: 8px; }
.plan-time { color: #c0c4cc; font-size: 12px; }
.quick-actions { display: flex; gap: 16px; flex-wrap: wrap; }
.qa-card { flex: 1; min-width: 200px; cursor: pointer; text-align: center; }
.qa-icon { font-size: 32px; margin-bottom: 8px; }
.qa-desc { color: #909399; font-size: 12px; margin-top: 6px; }
</style>
