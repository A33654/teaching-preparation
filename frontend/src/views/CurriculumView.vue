<template>
  <div>
    <div class="page-header">
      <div>
        <h1>教材课标</h1>
        <div class="subtitle">学科 → 教材 → 章节树，章节自动同步为 Neo4j 知识点节点</div>
      </div>
      <div class="header-actions">
        <el-button :icon="Plus" @click="subjectDialog = true">新增学科</el-button>
      </div>
    </div>

    <div class="curriculum-layout">
      <!-- 学科列表 -->
      <el-card class="left-panel" shadow="never">
        <template #header>学科</template>
        <div v-for="s in subjects" :key="s.id" class="subject-item" :class="{ active: currentSubject?.id === s.id }" @click="selectSubject(s)">
          <span>{{ s.name }}</span>
          <el-button size="small" text type="danger" @click.stop="removeSubject(s)">✕</el-button>
        </div>
        <el-empty v-if="!subjects.length" description="暂无学科" :image-size="60" />
      </el-card>

      <!-- 教材列表 -->
      <el-card class="mid-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <span>教材（{{ currentSubject?.name || "请选择学科" }}）</span>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="!currentSubject"
              @click="textbookDialog = true"
            >
              新增教材
            </el-button>
          </div>
        </template>
        <div v-for="t in textbooks" :key="t.id" class="textbook-item" :class="{ active: currentTextbook?.id === t.id }" @click="selectTextbook(t)">
          <div>
            <b>{{ t.name }}</b>
            <div class="textbook-meta">{{ t.version || "" }} {{ t.grade_level || "" }}</div>
          </div>
          <el-button size="small" text type="danger" @click.stop="removeTextbook(t)">✕</el-button>
        </div>
        <el-empty v-if="!textbooks.length" description="暂无教材" :image-size="60" />
      </el-card>

      <!-- 章节树 -->
      <el-card class="right-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <span>章节（{{ currentTextbook?.name || "请选择教材" }}）</span>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="!currentTextbook"
              @click="chapterDialog = true"
            >
              新增章节
            </el-button>
          </div>
        </template>
        <el-tree
          :data="chapterTree"
          node-key="id"
          default-expand-all
          :expand-on-click-node="false"
        >
          <template #default="{ data }">
            <div class="chapter-node">
              <span>{{ data.title }}</span>
              <span class="chapter-actions">
                <el-tooltip v-if="data.knowledge_point_id" content="已同步到知识图谱">
                  <el-tag size="small" type="warning" effect="plain">图</el-tag>
                </el-tooltip>
                <el-button size="small" text :icon="Edit" @click.stop="renameChapter(data)" />
                <el-button size="small" text :icon="Plus" @click.stop="addChildChapter(data)" />
                <el-button size="small" text type="danger" :icon="Delete" @click.stop="removeChapter(data)" />
              </span>
            </div>
          </template>
        </el-tree>
        <el-empty v-if="!chapterTree.length" description="暂无章节" :image-size="60" />
      </el-card>
    </div>

    <!-- 学科对话框 -->
    <el-dialog v-model="subjectDialog" title="新增学科" width="400px">
      <el-form label-width="70px">
        <el-form-item label="名称" required>
          <el-input v-model="subjectForm.name" placeholder="如：数学" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="subjectForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subjectDialog = false">取消</el-button>
        <el-button type="primary" @click="createSubject">保存</el-button>
      </template>
    </el-dialog>

    <!-- 教材对话框 -->
    <el-dialog v-model="textbookDialog" title="新增教材" width="420px">
      <el-form label-width="70px">
        <el-form-item label="名称" required>
          <el-input v-model="textbookForm.name" placeholder="如：人教版七年级数学上册" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="textbookForm.version" placeholder="如：人教版" />
        </el-form-item>
        <el-form-item label="学段">
          <el-select v-model="textbookForm.grade_level" clearable placeholder="选择学段">
            <el-option label="小学" value="小学" />
            <el-option label="初中" value="初中" />
            <el-option label="高中" value="高中" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="textbookForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="textbookDialog = false">取消</el-button>
        <el-button type="primary" @click="createTextbook">保存</el-button>
      </template>
    </el-dialog>

    <!-- 章节对话框 -->
    <el-dialog v-model="chapterDialog" :title="chapterParent ? `在「${chapterParent.title}」下新增章节` : '新增章节'" width="400px">
      <el-form label-width="70px">
        <el-form-item label="标题" required>
          <el-input v-model="chapterTitle" placeholder="如：第一章 有理数" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="chapterDialog = false">取消</el-button>
        <el-button type="primary" @click="createChapter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Delete, Edit, Plus } from "@element-plus/icons-vue"
import { curriculumApi } from "@/api"
import type { Chapter, Subject, Textbook } from "@/types"

const subjects = ref<Subject[]>([])
const textbooks = ref<Textbook[]>([])
const chapterTree = ref<Chapter[]>([])
const currentSubject = ref<Subject | null>(null)
const currentTextbook = ref<Textbook | null>(null)

const subjectDialog = ref(false)
const textbookDialog = ref(false)
const chapterDialog = ref(false)
const chapterParent = ref<Chapter | null>(null)
const chapterTitle = ref("")
const subjectForm = reactive({ name: "", description: "" })
const textbookForm = reactive({
  name: "",
  version: "",
  grade_level: null as string | null,
  description: "",
})

async function loadSubjects() {
  const resp = await curriculumApi.subjects()
  subjects.value = resp.data.data
}

async function loadTextbooks(subjectId?: string) {
  const resp = await curriculumApi.textbooks(subjectId || "")
  textbooks.value = resp.data.data
}

async function loadChapters(textbookId: string) {
  const resp = await curriculumApi.chapters(textbookId)
  chapterTree.value = resp as unknown as Chapter[]
}

function selectSubject(s: Subject) {
  currentSubject.value = s
  currentTextbook.value = null
  chapterTree.value = []
  loadTextbooks(s.id)
}

function selectTextbook(t: Textbook) {
  currentTextbook.value = t
  loadChapters(t.id)
}

async function createSubject() {
  if (!subjectForm.name.trim()) {
    ElMessage.warning("请输入学科名称")
    return
  }
  await curriculumApi.createSubject({ ...subjectForm })
  ElMessage.success("学科已创建")
  subjectDialog.value = false
  subjectForm.name = ""
  subjectForm.description = ""
  loadSubjects()
}

async function removeSubject(s: Subject) {
  await ElMessageBox.confirm(`删除学科「${s.name}」？其下教材与章节也会被删除`, "警告", { type: "warning" })
  await curriculumApi.deleteSubject(s.id)
  if (currentSubject.value?.id === s.id) {
    currentSubject.value = null
    currentTextbook.value = null
    textbooks.value = []
    chapterTree.value = []
  }
  loadSubjects()
}

async function createTextbook() {
  if (!textbookForm.name.trim() || !currentSubject.value) {
    ElMessage.warning("请输入教材名称")
    return
  }
  await curriculumApi.createTextbook({ ...textbookForm, subject_id: currentSubject.value.id })
  ElMessage.success("教材已创建")
  textbookDialog.value = false
  textbookForm.name = ""
  loadTextbooks(currentSubject.value.id)
}

async function removeTextbook(t: Textbook) {
  await ElMessageBox.confirm(`删除教材「${t.name}」？`, "警告", { type: "warning" })
  await curriculumApi.deleteTextbook(t.id)
  if (currentTextbook.value?.id === t.id) {
    currentTextbook.value = null
    chapterTree.value = []
  }
  loadTextbooks(currentSubject.value?.id || "")
}

function addChildChapter(parent?: Chapter) {
  chapterParent.value = parent || null
  chapterTitle.value = ""
  chapterDialog.value = true
}

async function createChapter() {
  if (!chapterTitle.value.trim() || !currentTextbook.value) {
    ElMessage.warning("请输入章节标题")
    return
  }
  await curriculumApi.createChapter({
    title: chapterTitle.value.trim(),
    parent_id: chapterParent.value?.id || null,
    textbook_id: currentTextbook.value.id,
    level: chapterParent.value ? (chapterParent.value.level || 1) + 1 : 1,
  })
  ElMessage.success("章节已创建（已同步到知识图谱）")
  chapterDialog.value = false
  chapterParent.value = null
  loadChapters(currentTextbook.value.id)
}

async function renameChapter(ch: Chapter) {
  const { value } = await ElMessageBox.prompt("修改章节标题", "编辑", {
    inputValue: ch.title,
  })
  await curriculumApi.updateChapter(ch.id, value || ch.title)
  loadChapters(currentTextbook.value!.id)
}

async function removeChapter(ch: Chapter) {
  await ElMessageBox.confirm(`删除章节「${ch.title}」？`, "警告", { type: "warning" })
  await curriculumApi.deleteChapter(ch.id)
  loadChapters(currentTextbook.value!.id)
}

onMounted(() => {
  loadSubjects()
  loadTextbooks()
})
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}

.curriculum-layout {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.left-panel {
  width: 220px;
  flex-shrink: 0;
}

.mid-panel {
  width: 280px;
  flex-shrink: 0;
}

.right-panel {
  flex: 1;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.subject-item,
.textbook-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  font-size: 14px;
}

.subject-item:hover,
.textbook-item:hover {
  background: #f5f7fa;
}

.subject-item.active,
.textbook-item.active {
  background: #fdf2f8;
  color: #ec4899;
  font-weight: 600;
}

.textbook-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.chapter-node {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex: 1;
  padding-right: 8px;
}

.chapter-actions {
  display: none;
  gap: 2px;
}

.chapter-node:hover .chapter-actions {
  display: inline-flex;
}
</style>
