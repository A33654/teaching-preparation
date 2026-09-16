<template>
  <div class="chat-wrap">
    <div class="page-header">
      <div>
        <h1>✨ AI 教学助手</h1>
        <div class="subtitle">基于 LangGraph Agent + Neo4j 知识图谱的智能问答与备课</div>
      </div>
      <el-tag type="info" effect="plain">LangGraph ReAct</el-tag>
    </div>

    <div ref="scrollRef" class="chat-box card-panel chat-scroll">
      <template v-if="messages.length === 0">
        <div class="empty">
          <div class="empty-icon">🤖</div>
          <p>你好{{ userName }}！我是基于知识图谱的 AI 教学助手。</p>
          <p class="empty-sub">我可以检索你的知识图谱与文档库，回答教学问题、梳理知识脉络。</p>
          <div class="suggestions">
            <el-button
              v-for="q in suggestions"
              :key="q"
              size="small"
              round
              @click="send(q)"
            >
              {{ q }}
            </el-button>
          </div>
        </div>
      </template>

      <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
        <div class="bubble">
          <div class="bubble-text">{{ m.text }}</div>
          <div v-if="m.sources.length" class="sources">
            <span class="sources-label">参考来源：</span>
            <el-tag
              v-for="(s, si) in m.sources"
              :key="si"
              size="small"
              :type="s.type === 'document' ? 'success' : 'warning'"
              effect="plain"
              class="source-tag"
            >
              {{ s.name }}
            </el-tag>
          </div>
        </div>
      </div>

      <div v-if="toolActive" class="msg-row assistant">
        <div class="bubble tool-bubble">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在检索：{{ toolActive }}</span>
        </div>
      </div>
    </div>

    <div class="input-bar">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="输入问题，基于知识图谱回答...（Enter 发送，Shift+Enter 换行）"
        :disabled="loading"
        @keydown.enter.exact.prevent="send()"
      />
      <el-button
        type="primary"
        class="send-btn"
        :loading="loading"
        :disabled="!input.trim()"
        @click="send()"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue"
import { ElMessage } from "element-plus"
import { Loading } from "@element-plus/icons-vue"
import { streamChat } from "@/api"
import { useAuthStore } from "@/stores/auth"
import type { ChatMessage } from "@/types"

const auth = useAuthStore()

interface UiMessage {
  role: "user" | "assistant"
  text: string
  sources: { type: string; name: string; id: string }[]
}

const messages = ref<UiMessage[]>([])
const input = ref("")
const loading = ref(false)
const toolActive = ref("")
const scrollRef = ref<HTMLElement>()

const userName = computed(() => auth.user?.full_name || auth.user?.nickname || "")

const suggestions = [
  "我上传的文档中有哪些知识点？",
  "梳理一下知识图谱中的核心考点",
  "帮我梳理某个知识点的前置知识",
  "今天有哪些教学任务？",
]

async function scrollToBottom() {
  await nextTick()
  scrollRef.value?.scrollTo({ top: scrollRef.value.scrollHeight, behavior: "smooth" })
}

async function send(preset?: string) {
  const text = (preset ?? input.value).trim()
  if (!text || loading.value) return
  input.value = ""

  messages.value.push({ role: "user", text, sources: [] })
  const assistantMsg: UiMessage = { role: "assistant", text: "", sources: [] }
  messages.value.push(assistantMsg)
  loading.value = true
  toolActive.value = ""
  await scrollToBottom()

  // 历史消息（不含当前这轮）
  const history: ChatMessage[] = messages.value
    .slice(0, -2)
    .map((m) => ({ role: m.role, content: m.text }))

  try {
    for await (const event of streamChat(text, history)) {
      if (event.type === "token" && event.content) {
        assistantMsg.text += event.content
        await scrollToBottom()
      } else if (event.type === "tool_result") {
        toolActive.value = toolNameLabel(event.tool_name || "")
        for (const s of event.sources || []) {
          if (!assistantMsg.sources.some((x) => x.id === s.id)) {
            assistantMsg.sources.push(s)
          }
        }
      } else if (event.type === "done") {
        for (const s of event.sources || []) {
          if (!assistantMsg.sources.some((x) => x.id === s.id)) {
            assistantMsg.sources.push(s)
          }
        }
        // 后端 LLM 非流式时 token 事件缺失，完整回复在 done.reply 里
        if (!assistantMsg.text) assistantMsg.text = event.reply || "（无内容）"
      } else if (event.type === "error") {
        assistantMsg.text = assistantMsg.text || `出错了：${event.content}`
        ElMessage.error(String(event.content))
      }
    }
  } catch (e: any) {
    assistantMsg.text = assistantMsg.text || "请求失败，请稍后重试"
    ElMessage.error(String(e.message || e))
  } finally {
    loading.value = false
    toolActive.value = ""
    await scrollToBottom()
  }
}

function toolNameLabel(name: string): string {
  const map: Record<string, string> = {
    search_knowledge_graph: "知识图谱",
    get_knowledge_point_detail: "知识点详情",
    get_knowledge_neighbors: "知识脉络",
    search_documents: "文档库",
  }
  return map[name] || name
}
</script>

<style scoped>
.chat-wrap {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  max-width: 960px;
  margin: 0 auto;
}

.chat-box {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  margin-bottom: 16px;
}

.empty {
  text-align: center;
  padding: 60px 20px;
  color: #606266;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 16px;
}

.empty-sub {
  color: #909399;
  font-size: 13px;
}

.suggestions {
  margin-top: 20px;
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

.msg-row {
  display: flex;
  margin-bottom: 16px;
}

.msg-row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-row.user .bubble {
  background: #ec4899;
  color: #fff;
  border-top-right-radius: 2px;
}

.msg-row.assistant .bubble {
  background: #f4f4f5;
  color: #303133;
  border-top-left-radius: 2px;
}

.tool-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  font-size: 13px;
  background: #fafafa;
  border: 1px dashed #e4e7ed;
}

.sources {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.sources-label {
  font-size: 12px;
  color: #909399;
}

.source-tag {
  margin: 0;
}

.input-bar {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.send-btn {
  height: 56px;
  width: 90px;
}
</style>
