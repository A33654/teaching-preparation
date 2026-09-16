<template>
  <div>
    <div class="page-header">
      <div>
        <h1>知识图谱</h1>
        <div class="subtitle">Neo4j 存储的知识点关系网络（点击节点查看详情，Shift+点击建立关系）</div>
      </div>
      <div class="header-actions">
        <el-button :icon="Plus" @click="addDialog = true">新增知识点</el-button>
        <el-radio-group v-model="view" size="default">
          <el-radio-button value="graph">图谱视图</el-radio-button>
          <el-radio-button value="table">列表视图</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 图谱视图 -->
    <div v-if="view === 'graph'" class="graph-layout">
      <div v-loading="graphLoading" class="card-panel graph-panel">
        <div v-if="!graphLoading && nodes.length === 0" class="graph-empty">
          <el-empty description="暂无知识点，上传文档后可自动抽取生成，或手动新增" />
        </div>
        <div ref="graphRef" class="graph-container" :style="{ display: nodes.length ? 'block' : 'none' }" />
      </div>

      <!-- 节点详情 -->
      <el-card v-if="selected" class="detail-panel" shadow="never">
        <template #header>
          <div class="detail-head">
            <b>{{ selected.name }}</b>
            <el-button size="small" text type="danger" @click="selected = null">✕</el-button>
          </div>
        </template>
        <div class="detail-body">
          <el-tag size="small" effect="plain">{{ selected.subject }}</el-tag>
          <el-tag v-if="selected.is_key_point" size="small" type="danger" effect="plain">核心考点</el-tag>
          <p class="detail-desc">{{ selected.description || "暂无描述" }}</p>
          <div class="detail-ops">
            <el-button size="small" :icon="Edit" @click="openEdit(selected)">编辑</el-button>
            <el-popconfirm title="删除该知识点及其所有关系？" @confirm="removeKp(selected)">
              <template #reference>
                <el-button size="small" type="danger" plain :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
          <template v-if="detailRelations.length">
            <div class="rel-title">关系（{{ detailRelations.length }}）</div>
            <div v-for="(r, i) in detailRelations" :key="i" class="rel-row">
              <el-tag size="small" :type="relTagType(r.relation_type)" effect="plain">
                {{ RELATION_LABELS[r.relation_type] || r.relation_type }}
              </el-tag>
              <span class="rel-arrow">{{ r.source_id === selected.id ? "→" : "←" }}</span>
              <span class="rel-name">{{ nodeName(r.source_id === selected.id ? r.target_id : r.source_id) }}</span>
              <el-button
                size="small"
                text
                type="danger"
                @click="deleteRelation(selected, r)"
              >
                删除
              </el-button>
            </div>
          </template>
        </div>
      </el-card>
    </div>

    <!-- 列表视图 -->
    <div v-else class="card-panel">
      <div class="toolbar">
        <el-input
          v-model="filter.search"
          placeholder="按名称搜索"
          clearable
          style="width: 240px"
          :prefix-icon="Search"
        />
        <el-select v-model="filter.subject" placeholder="按学科筛选" clearable style="width: 180px">
          <el-option v-for="s in subjects" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button :icon="Refresh" @click="loadTable">刷新</el-button>
      </div>
      <el-table v-loading="tableLoading" :data="tableData" stripe>
        <el-table-column prop="name" label="知识点" min-width="180">
          <template #default="{ row }">
            <b>{{ row.name }}</b>
            <el-tag v-if="row.is_key_point" size="small" type="danger" effect="plain" style="margin-left: 6px">
              核心
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="学科" width="120" />
        <el-table-column label="难度" width="140">
          <template #default="{ row }">{{ "⭐".repeat(row.difficulty || 1) }}</template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="260" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="locateInGraph(row.id)">定位图谱</el-button>
            <el-button size="small" :icon="Edit" @click="openEdit(row)" />
            <el-popconfirm title="删除该知识点？" @confirm="removeKp(row)">
              <template #reference>
                <el-button size="small" type="danger" plain :icon="Delete" />
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        :total="total"
        :page-size="pageSize"
        layout="total, prev, pager, next"
        class="pager"
        @current-change="loadTable"
      />
    </div>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="addDialog" :title="editing ? '编辑知识点' : '新增知识点'" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：勾股定理" />
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="form.subject" placeholder="如：数学" />
        </el-form-item>
        <el-form-item label="学段">
          <el-select v-model="form.grade_level" clearable placeholder="选择学段">
            <el-option label="小学" value="小学" />
            <el-option label="初中" value="初中" />
            <el-option label="高中" value="高中" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-rate v-model="form.difficulty" />
        </el-form-item>
        <el-form-item label="核心考点">
          <el-switch v-model="form.is_key_point" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveKp">保存</el-button>
      </template>
    </el-dialog>

    <!-- 创建关系对话框 -->
    <el-dialog v-model="relDialog" title="创建知识点关系" width="480px">
      <p class="rel-hint">
        {{ relationSource?.name }} → <el-select v-model="relForm.relation_type" style="width: 150px">
          <el-option label="前置知识" value="prerequisite" />
          <el-option label="包含" value="contains" />
          <el-option label="相关" value="related_to" />
        </el-select> → {{ relationTarget?.name }}
      </p>
      <template #footer>
        <el-button @click="relDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmRelation">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { Delete, Edit, Plus, Refresh, Search } from "@element-plus/icons-vue"
import { DataSet } from "vis-data"
import { Network, type Node, type Edge } from "vis-network"
import { knowledgeGraphApi } from "@/api"
import type { KnowledgePoint, KnowledgeRelation } from "@/types"

const RELATION_LABELS: Record<string, string> = {
  prerequisite: "前置",
  contains: "包含",
  related_to: "关联",
}

const RELATION_COLORS: Record<string, { color: string }> = {
  prerequisite: { color: "#f59e0b" },
  contains: { color: "#ec4899" },
  related_to: { color: "#a78bfa" },
}

const view = ref<"graph" | "table">("graph")
const graphRef = ref<HTMLElement>()
const graphLoading = ref(false)
const nodes = ref<KnowledgePoint[]>([])
const edges = ref<KnowledgeRelation[]>([])
const selected = ref<KnowledgePoint | null>(null)
const detailRelations = ref<KnowledgeRelation[]>([])
let network: Network | null = null

// 列表
const tableLoading = ref(false)
const tableData = ref<KnowledgePoint[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filter = reactive({ search: "", subject: "" })
const subjects = computed(() => [...new Set(tableData.value.map((k) => k.subject))])

// 表单
const addDialog = ref(false)
const saving = ref(false)
const editing = ref<KnowledgePoint | null>(null)
const form = reactive({
  name: "",
  subject: "通用",
  grade_level: null as string | null,
  difficulty: 1,
  is_key_point: false,
  description: "",
})

// 关系创建（Shift+点击）
const relDialog = ref(false)
const relationSource = ref<KnowledgePoint | null>(null)
const relationTarget = ref<KnowledgePoint | null>(null)
const relForm = reactive({ relation_type: "related_to" })
let shiftFirst: string | null = null

function relTagType(t: string): "warning" | "danger" | "success" {
  if (t === "prerequisite") return "warning"
  if (t === "contains") return "danger"
  return "success"
}

function nodeName(id: string): string {
  return nodes.value.find((n) => n.id === id)?.name || id
}

// ==================== 图谱 ====================

async function loadGraph() {
  graphLoading.value = true
  try {
    const resp = await knowledgeGraphApi.fullGraph()
    nodes.value = resp.data.nodes
    edges.value = resp.data.edges
    await nextTick()
    renderGraph()
  } catch {
    // 拦截器已提示
  } finally {
    graphLoading.value = false
  }
}

function renderGraph() {
  if (!graphRef.value || nodes.value.length === 0) return
  if (network) {
    network.destroy()
    network = null
  }

  const visNodes: Node[] = nodes.value.map((n) => {
    const isKey = n.is_key_point
    return {
      id: n.id,
      label: n.name,
      title: `<div style="padding:8px"><b>${n.name}</b><br/><span>${n.subject || ""} · 难度 ${"⭐".repeat(n.difficulty || 1)}</span>${isKey ? '<br/><span style="color:#e11d48">🔴 核心考点</span>' : ""}<br/><span style="color:#9ca3af;font-size:12px">${(n.description || "").slice(0, 60)}</span></div>`,
      color: isKey
        ? { background: "#fb7185", border: "#e11d48", hover: { background: "#fda4af", border: "#be123c" } }
        : { background: "#f9a8d4", border: "#ec4899", hover: { background: "#fbcfe8", border: "#db2777" } },
      font: { color: isKey ? "#fff" : "#831843", size: 13 },
      shape: "box",
      borderWidth: isKey ? 3 : 2,
      margin: { top: 10, right: 16, bottom: 10, left: 16 },
      widthConstraint: { minimum: 60, maximum: 180 },
    }
  })

  const visEdges: Edge[] = edges.value.map((e) => ({
    id: `${e.source_id}-${e.target_id}-${e.relation_type}`,
    from: e.source_id,
    to: e.target_id,
    label: RELATION_LABELS[e.relation_type] || "",
    arrows: { to: { enabled: true, scaleFactor: 0.8 } },
    color: RELATION_COLORS[e.relation_type] || { color: "#d1d5db" },
    width: 2,
    font: { size: 11, color: "#9ca3af", background: "#fff", strokeWidth: 0 },
    smooth: { enabled: true, type: "curvedCW", roundness: 0.3 },
  }))

  network = new Network(
    graphRef.value,
    { nodes: new DataSet(visNodes as any), edges: new DataSet(visEdges as any) },
    {
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -35,
          centralGravity: 0.005,
          springLength: 150,
          springConstant: 0.08,
          damping: 0.4,
        },
        stabilization: { iterations: 100 },
      },
      interaction: { hover: true, tooltipDelay: 150, zoomView: true, dragView: true },
      edges: { smooth: { enabled: true, type: "curvedCW", roundness: 0.3 } },
      layout: { improvedLayout: true },
    },
  )

  network.on("click", (params: any) => {
    const nid = params.nodes?.[0] as string | undefined
    const shift = params.event?.srcEvent?.shiftKey
    if (!nid) return

    const node = nodes.value.find((n) => n.id === nid)
    if (!node) return

    if (shift) {
      if (!shiftFirst) {
        shiftFirst = nid
        relationSource.value = node
        ElMessage.info("再 Shift+点击另一个节点以创建关系")
      } else if (shiftFirst !== nid) {
        relationTarget.value = node
        relDialog.value = true
        shiftFirst = null
      }
      return
    }
    shiftFirst = null
    selectNode(node)
  })
}

async function selectNode(node: KnowledgePoint) {
  selected.value = node
  try {
    const resp = await knowledgeGraphApi.relations(node.id)
    detailRelations.value = resp.data
  } catch {
    detailRelations.value = []
  }
}

async function confirmRelation() {
  if (!relationSource.value || !relationTarget.value) return
  await knowledgeGraphApi.createRelation(relationSource.value.id, {
    target_id: relationTarget.value.id,
    relation_type: relForm.relation_type,
  })
  ElMessage.success("关系已创建")
  relDialog.value = false
  relationSource.value = null
  relationTarget.value = null
  loadGraph()
}

async function deleteRelation(source: KnowledgePoint, r: KnowledgeRelation) {
  await knowledgeGraphApi.deleteRelation(r.source_id, {
    target_id: r.target_id,
    relation_type: r.relation_type,
  })
  ElMessage.success("关系已删除")
  selected.value = null
  loadGraph()
}

function locateInGraph(id: string) {
  view.value = "graph"
  loadGraph().then(() => {
    setTimeout(() => {
      network?.selectNodes([id])
      const pos = network?.getPositions([id])?.[id]
      if (pos) network?.moveTo({ position: pos, scale: 1 })
      const node = nodes.value.find((n) => n.id === id)
      if (node) selectNode(node)
    }, 300)
  })
}

// ==================== 列表 ====================

async function loadTable() {
  tableLoading.value = true
  try {
    const resp = await knowledgeGraphApi.list({
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
      search: filter.search || undefined,
      subject: filter.subject || undefined,
    })
    tableData.value = resp.data.data
    total.value = resp.data.count
  } finally {
    tableLoading.value = false
  }
}

// ==================== CRUD ====================

function openEdit(kp: KnowledgePoint) {
  editing.value = kp
  form.name = kp.name
  form.subject = kp.subject
  form.grade_level = kp.grade_level || null
  form.difficulty = kp.difficulty || 1
  form.is_key_point = kp.is_key_point
  form.description = kp.description || ""
  addDialog.value = true
}

async function saveKp() {
  if (!form.name.trim()) {
    ElMessage.warning("请输入知识点名称")
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await knowledgeGraphApi.update(editing.value.id, { ...form })
    } else {
      await knowledgeGraphApi.create({ ...form })
    }
    ElMessage.success(editing.value ? "已更新" : "已创建")
    addDialog.value = false
    editing.value = null
    form.name = ""
    form.description = ""
    if (view.value === "graph") loadGraph()
    else loadTable()
  } finally {
    saving.value = false
  }
}

async function removeKp(kp: KnowledgePoint) {
  await knowledgeGraphApi.remove(kp.id)
  ElMessage.success("已删除")
  selected.value = null
  if (view.value === "graph") loadGraph()
  else loadTable()
}

onMounted(() => {
  loadGraph()
  loadTable()
})

onBeforeUnmount(() => {
  network?.destroy()
  network = null
})
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.graph-layout {
  display: flex;
  gap: 16px;
}

.graph-panel {
  flex: 1;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.graph-container {
  width: 100%;
  height: 620px;
}

.graph-empty {
  width: 100%;
}

.detail-panel {
  width: 300px;
  flex-shrink: 0;
  height: fit-content;
  max-height: 700px;
  overflow-y: auto;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}

.detail-desc {
  margin: 0;
  color: #606266;
  line-height: 1.6;
}

.detail-ops {
  display: flex;
  gap: 8px;
}

.rel-title {
  font-weight: 600;
  color: #303133;
  margin-top: 4px;
}

.rel-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.rel-arrow {
  color: #909399;
}

.rel-name {
  flex: 1;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rel-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
