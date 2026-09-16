<template>
  <div>
    <div class="page-header">
      <div>
        <h1>备忘提醒</h1>
        <div class="subtitle">课程表 + 教学任务管理</div>
      </div>
      <el-button :icon="Plus" @click="taskDialog = true">新增任务</el-button>
    </div>

    <!-- 今日概览 -->
    <el-card v-if="today" class="today-card" shadow="never">
      <template #header>
        <b>今日（{{ today.day_name }}）</b>
      </template>
      <div class="today-body">
        <div class="today-col">
          <div class="today-label">📅 今日课程</div>
          <template v-if="today.today_schedule.length">
            <div v-for="s in today.today_schedule" :key="s.id" class="today-item">
              {{ s.start_time }}-{{ s.end_time }} {{ s.subject }}
              <span v-if="s.classroom" class="muted">@{{ s.classroom }}</span>
            </div>
          </template>
          <div v-else class="muted">无课程安排</div>
        </div>
        <el-divider direction="vertical" />
        <div class="today-col">
          <div class="today-label">✅ 待办任务</div>
          <template v-if="today.upcoming_tasks.length">
            <div v-for="t in today.upcoming_tasks" :key="t.id" class="today-item">
              <el-checkbox :model-value="t.completed" @change="toggleTask(t)">{{ t.title }}</el-checkbox>
            </div>
          </template>
          <div v-else class="muted">暂无待办</div>
        </div>
      </div>
    </el-card>

    <div class="two-col">
      <!-- 课程表 -->
      <el-card class="card-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <b>课程表</b>
            <el-button size="small" type="primary" plain @click="scheduleDialog = true">添加课程</el-button>
          </div>
        </template>
        <el-table :data="schedules" size="small">
          <el-table-column label="星期" width="90">
            <template #default="{ row }">{{ DAY_NAMES[row.day_of_week] }}</template>
          </el-table-column>
          <el-table-column label="时间" width="140">
            <template #default="{ row }">{{ row.start_time }} - {{ row.end_time }}</template>
          </el-table-column>
          <el-table-column prop="subject" label="课程" min-width="140" />
          <el-table-column prop="classroom" label="教室" width="100" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-popconfirm title="删除该课程？" @confirm="removeSchedule(row)">
                <template #reference>
                  <el-button size="small" text type="danger" :icon="Delete" />
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 任务 -->
      <el-card class="card-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <b>教学任务</b>
            <el-switch
              v-model="showCompleted"
              active-text="显示已完成"
              size="small"
              @change="loadTasks"
            />
          </div>
        </template>
        <el-table :data="tasks" size="small">
          <el-table-column width="50">
            <template #default="{ row }">
              <el-checkbox :model-value="row.completed" @change="toggleTask(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="title" label="任务" min-width="160">
            <template #default="{ row }">
              <span :class="{ done: row.completed }">{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="priorityType(row.priority)" effect="plain">
                {{ priorityLabel(row.priority) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="due_date" label="截止" width="110">
            <template #default="{ row }">{{ row.due_date || "—" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-popconfirm title="删除该任务？" @confirm="removeTask(row)">
                <template #reference>
                  <el-button size="small" text type="danger" :icon="Delete" />
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 添加课程对话框 -->
    <el-dialog v-model="scheduleDialog" title="添加课程" width="420px">
      <el-form label-width="70px">
        <el-form-item label="星期" required>
          <el-select v-model="scheduleForm.day_of_week" style="width: 100%">
            <el-option v-for="(name, i) in DAY_NAMES" :key="i" :label="name" :value="i" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间" required>
          <div style="display: flex; gap: 8px; width: 100%">
            <el-time-select v-model="scheduleForm.start_time" start="07:00" step="00:10" end="21:00" placeholder="开始" style="flex: 1" />
            <el-time-select v-model="scheduleForm.end_time" start="07:00" step="00:10" end="21:00" placeholder="结束" style="flex: 1" />
          </div>
        </el-form-item>
        <el-form-item label="课程" required>
          <el-input v-model="scheduleForm.subject" placeholder="如：数学" />
        </el-form-item>
        <el-form-item label="教室">
          <el-input v-model="scheduleForm.classroom" placeholder="如：3号楼201" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scheduleDialog = false">取消</el-button>
        <el-button type="primary" @click="createSchedule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增任务对话框 -->
    <el-dialog v-model="taskDialog" title="新增任务" width="440px">
      <el-form label-width="70px">
        <el-form-item label="任务" required>
          <el-input v-model="taskForm.title" placeholder="如：批改第三章作业" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="taskForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="taskForm.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-radio-group v-model="taskForm.priority">
            <el-radio-button value="high">高</el-radio-button>
            <el-radio-button value="normal">中</el-radio-button>
            <el-radio-button value="low">低</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button type="primary" @click="createTask">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { Delete, Plus } from "@element-plus/icons-vue"
import { remindersApi } from "@/api"
import type { Schedule, TaskItem, TodayOverview } from "@/types"

const DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

const schedules = ref<Schedule[]>([])
const tasks = ref<TaskItem[]>([])
const today = ref<TodayOverview | null>(null)
const showCompleted = ref(false)

const scheduleDialog = ref(false)
const taskDialog = ref(false)
const scheduleForm = reactive({
  day_of_week: 0,
  start_time: "08:00",
  end_time: "09:00",
  subject: "",
  classroom: "",
})
const taskForm = reactive({
  title: "",
  description: "",
  due_date: "",
  priority: "normal",
})

async function loadAll() {
  const [s, t, td] = await Promise.all([
    remindersApi.schedules(),
    remindersApi.tasks(showCompleted.value),
    remindersApi.today(),
  ])
  schedules.value = s.data.data
  tasks.value = t.data.data
  today.value = td.data
}

async function loadTasks() {
  const resp = await remindersApi.tasks(showCompleted.value)
  tasks.value = resp.data.data
}

async function createSchedule() {
  if (!scheduleForm.subject || !scheduleForm.start_time || !scheduleForm.end_time) {
    ElMessage.warning("请填写完整课程信息")
    return
  }
  await remindersApi.createSchedule({ ...scheduleForm })
  ElMessage.success("课程已添加")
  scheduleDialog.value = false
  scheduleForm.subject = ""
  loadAll()
}

async function removeSchedule(row: Schedule) {
  await remindersApi.deleteSchedule(row.id)
  loadAll()
}

async function createTask() {
  if (!taskForm.title.trim()) {
    ElMessage.warning("请输入任务名称")
    return
  }
  await remindersApi.createTask({ ...taskForm })
  ElMessage.success("任务已创建")
  taskDialog.value = false
  taskForm.title = ""
  taskForm.description = ""
  loadAll()
}

async function toggleTask(row: TaskItem) {
  await remindersApi.toggleTask(row.id)
  loadAll()
}

async function removeTask(row: TaskItem) {
  await remindersApi.deleteTask(row.id)
  loadAll()
}

function priorityLabel(p: string): string {
  return { high: "高", normal: "中", low: "低" }[p] || p
}

function priorityType(p: string): "danger" | "warning" | "info" {
  if (p === "high") return "danger"
  if (p === "low") return "info"
  return "warning"
}

onMounted(loadAll)
</script>

<style scoped>
.today-card {
  margin-bottom: 16px;
}

.today-body {
  display: flex;
  gap: 20px;
}

.today-col {
  flex: 1;
}

.today-label {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
}

.today-item {
  padding: 4px 0;
  font-size: 14px;
}

.two-col {
  display: flex;
  gap: 16px;
}

.two-col > * {
  flex: 1;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.done {
  text-decoration: line-through;
  color: #c0c4cc;
}

.muted {
  color: #909399;
  font-size: 13px;
}
</style>
