// 类型化 API 封装（对应后端 /api/v1 路由）
import client, { authorizedFetch, TOKEN_KEY } from "./client"

export { authorizedFetch, TOKEN_KEY } from "./client"
import type {
  AdminStatsData,
  AiGenerateRequest,
  AiGenerateResponse,
  CandidateCreate,
  CandidateKp,
  CandidatesPublic,
  DocumentItem,
  DocumentsPublic,
  ExtractionLogsPublic,
  ExtractionResult,
  GraphData,
  KnowledgePoint,
  KnowledgePointsPublic,
  KnowledgeRelation,
  LessonPlan,
  LessonPlansPublic,
  Message,
  PptRecord,
  PptRecordsPublic,
  Schedule,
  SlideContent,
  Subject,
  SubjectDashboard,
  SummarizeResult,
  TaskItem,
  Textbook,
  TodayOverview,
  UserPublic,
  UsersPublic,
} from "@/types"

// ==================== 认证 ====================

export const authApi = {
  login: (username: string, password: string) =>
    client.postForm<{ access_token: string; token_type: string }>("/login/access-token", {
      username,
      password,
    }),
  signup: (data: { email: string; password: string; full_name?: string }) =>
    client.post<UserPublic>("/users/signup", data),
  recoverPassword: (email: string) =>
    client.post<Message>(`/password-recovery/${email}`),
  resetPassword: (data: { token: string; new_password: string }) =>
    client.post<Message>("/reset-password/", data),
  me: () => client.get<UserPublic>("/users/me"),
  updateMe: (data: Record<string, unknown>) =>
    client.patch<UserPublic>("/users/me", data),
  updatePassword: (data: { current_password: string; new_password: string }) =>
    client.patch<Message>("/users/me/password", data),
}

// ==================== 知识图谱 ====================

export const knowledgeGraphApi = {
  list: (params?: {
    skip?: number
    limit?: number
    subject?: string
    grade_level?: string
    search?: string
  }) => client.get<KnowledgePointsPublic>("/knowledge-points/", { params }),
  get: (id: string) => client.get<KnowledgePoint>(`/knowledge-points/${id}`),
  create: (data: {
    name: string
    subject?: string
    description?: string
    grade_level?: string | null
    difficulty?: number
    is_key_point?: boolean
  }) => client.post<KnowledgePoint>("/knowledge-points/", data),
  update: (id: string, data: Record<string, unknown>) =>
    client.put<KnowledgePoint>(`/knowledge-points/${id}`, data),
  remove: (id: string) => client.delete(`/knowledge-points/${id}`),
  fullGraph: () => client.get<GraphData>("/knowledge-points/graph/full"),
  subgraph: (id: string, depth = 2) =>
    client.get<GraphData>(`/knowledge-points/${id}/subgraph`, { params: { depth } }),
  relations: (id: string) =>
    client.get<KnowledgeRelation[]>(`/knowledge-points/${id}/relations`),
  createRelation: (id: string, data: { target_id: string; relation_type: string }) =>
    client.post<KnowledgeRelation>(`/knowledge-points/${id}/relations`, data),
  deleteRelation: (id: string, params: { target_id: string; relation_type?: string }) =>
    client.delete(`/knowledge-points/${id}/relations`, { params }),
  search: (query: string, top_k = 10) =>
    client.post<{ query: string; results: KnowledgePoint[] }>("/knowledge-points/search", {
      query,
      top_k,
    }),
  // 章节自动联动：检索本章知识点 + 前置依赖 + 知识库完整度判断
  chapterContext: (chapter: string, subject = "") =>
    client.post<{
      chapter: string
      knowledge_points: (KnowledgePoint & {
        prerequisites?: string[]
        exam_points?: { id: string; name: string; level: string; description?: string }[]
        misconceptions?: { id: string; content: string; correction?: string }[]
      })[]
      coverage: "complete" | "partial" | "missing"
      message: string
    }>("/knowledge-points/chapter-context", { chapter, subject }),
  // 考点实体（考纲要求：了解/理解/掌握）
  examPoints: (kpId: string) =>
    client.get<{ data: { id: string; name: string; level: string; description?: string }[] }>(
      `/knowledge-points/${kpId}/exam-points`,
    ),
  addExamPoint: (kpId: string, data: { name: string; level: string; description?: string }) =>
    client.post(`/knowledge-points/${kpId}/exam-points`, data),
  deleteExamPoint: (kpId: string, examId: string) =>
    client.delete(`/knowledge-points/${kpId}/exam-points/${examId}`),
  // 误区实体（学生常见错误概念）
  misconceptions: (kpId: string) =>
    client.get<{ data: { id: string; content: string; correction?: string }[] }>(
      `/knowledge-points/${kpId}/misconceptions`,
    ),
  addMisconception: (kpId: string, data: { content: string; correction?: string }) =>
    client.post(`/knowledge-points/${kpId}/misconceptions`, data),
  deleteMisconception: (kpId: string, misId: string) =>
    client.delete(`/knowledge-points/${kpId}/misconceptions/${misId}`),
}

// ==================== 文档 ====================

export const documentsApi = {
  list: (params?: { skip?: number; limit?: number }) =>
    client.get<DocumentsPublic>("/documents/", { params }),
  get: (id: string) => client.get<DocumentItem>(`/documents/${id}`),
  remove: (id: string) => client.delete(`/documents/${id}`),
  upload: (file: File, autoAnalyze = true) => {
    const form = new FormData()
    form.append("file", file)
    return client.post<DocumentItem>(
      `/documents/upload?auto_analyze=${autoAnalyze}`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    )
  },
  analyze: (id: string) =>
    client.post<{ document: DocumentItem; extraction: ExtractionResult }>(
      `/documents/${id}/analyze`,
    ),
  search: (query: string, top_k = 10) =>
    client.post<{
      query: string
      knowledge_points: KnowledgePoint[]
      documents: { id: string; filename: string; snippet: string }[]
    }>("/documents/search", { query, top_k }),
}

// ==================== 教案 ====================

export const lessonPlansApi = {
  list: (params?: { skip?: number; limit?: number }) =>
    client.get<LessonPlansPublic>("/lesson-plans/", { params }),
  get: (id: string) => client.get<LessonPlan>(`/lesson-plans/${id}`),
  create: (data: {
    title: string
    subject: string
    grade_level?: string | null
    teaching_objectives?: string | null
    teaching_process?: string | null
    knowledge_point_ids?: string[]
    subject_id?: string | null
  }) => client.post<LessonPlan>("/lesson-plans/", data),
  update: (id: string, data: Record<string, unknown>) =>
    client.put<LessonPlan>(`/lesson-plans/${id}`, data),
  remove: (id: string) => client.delete(`/lesson-plans/${id}`),
  aiGenerate: (data: AiGenerateRequest) =>
    client.post<AiGenerateResponse>("/lesson-plans/ai-generate", data),
  summarizeFile: (file: File) => {
    const form = new FormData()
    form.append("file", file)
    return client.post<SummarizeResult>("/lesson-plans/summarize", form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
  },
  exportUrl: (id: string) => `/api/v1/lesson-plans/${id}/export`,
}

// ==================== 概括 / PPT ====================

export const summarizeApi = {
  summarize: (file: File) => {
    const form = new FormData()
    form.append("file", file)
    return client.post<SummarizeResult>("/summarize/", form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
  },
  generatePpt: (file: File, style: string, slide_count: number) => {
    const form = new FormData()
    form.append("file", file)
    form.append("style", style)
    form.append("slide_count", String(slide_count))
    return client.post<Blob>("/summarize/generate-ppt", form, {
      responseType: "blob",
      headers: { "Content-Type": "multipart/form-data" },
    })
  },
  pptList: () => client.get<PptRecordsPublic>("/summarize/ppt-list"),
  savePpt: (id: string, slides: SlideContent[], style: string) =>
    client.put<Blob>(`/summarize/ppt/${id}/save`, { slides, style }, { responseType: "blob" }),
  pptExportUrl: (id: string) => `/api/v1/summarize/ppt/${id}/export`,
  pptRecord: (id: string) => {
    // 从列表缓存读取
    return null
  },
}

// ==================== 教材课标 ====================

export const curriculumApi = {
  subjects: () => client.get<{ data: Subject[]; count: number }>("/curriculum/subjects"),
  createSubject: (data: { name: string; description?: string | null }) =>
    client.post<Subject>("/curriculum/subjects", data),
  deleteSubject: (id: string) => client.delete(`/curriculum/subjects/${id}`),
  textbooks: (subjectId = "") =>
    client.get<{ data: Textbook[]; count: number }>("/curriculum/textbooks", {
      params: { subject_id: subjectId },
    }),
  createTextbook: (data: {
    name: string
    version?: string | null
    grade_level?: string | null
    cover_url?: string | null
    description?: string | null
    subject_id: string
  }) => client.post<Textbook>("/curriculum/textbooks", data),
  deleteTextbook: (id: string) => client.delete(`/curriculum/textbooks/${id}`),
  chapters: (textbookId: string) =>
    client.get(`/curriculum/chapters/${textbookId}`).then((r) => r.data as any[]),
  createChapter: (data: { title: string; parent_id?: string | null; textbook_id: string; level: number }) =>
    client.post("/curriculum/chapters", data),
  updateChapter: (id: string, title: string) =>
    client.put(`/curriculum/chapters/${id}`, null, { params: { title } }),
  deleteChapter: (id: string) => client.delete(`/curriculum/chapters/${id}`),
  reorderChapter: (id: string, params: { new_parent_id?: string; new_order?: number }) =>
    client.put(`/curriculum/chapters/${id}/reorder`, null, { params }),
  dashboard: (subjectId: string) =>
    client.get<SubjectDashboard>(`/curriculum/dashboard/${subjectId}`),
}

// ==================== 备忘提醒 ====================

export const remindersApi = {
  schedules: () => client.get<{ data: Schedule[]; count: number }>("/reminders/schedules"),
  createSchedule: (data: {
    day_of_week: number
    start_time: string
    end_time: string
    subject: string
    classroom?: string
  }) => client.post<Schedule>("/reminders/schedules", data),
  deleteSchedule: (id: string) => client.delete(`/reminders/schedules/${id}`),
  tasks: (showCompleted = false) =>
    client.get<{ data: TaskItem[]; count: number }>("/reminders/tasks", {
      params: { show_completed: showCompleted },
    }),
  createTask: (data: { title: string; description?: string; due_date?: string; priority?: string }) =>
    client.post<TaskItem>("/reminders/tasks", data),
  toggleTask: (id: string) => client.put<TaskItem>(`/reminders/tasks/${id}/toggle`),
  deleteTask: (id: string) => client.delete(`/reminders/tasks/${id}`),
  today: () => client.get<TodayOverview>("/reminders/today"),
}

// ==================== 管理员后台 ====================

export const adminApi = {
  users: (params?: { skip?: number; limit?: number }) =>
    client.get<UsersPublic>("/users/", { params }),
  updateUser: (id: string, data: Record<string, unknown>) =>
    client.patch<Record<string, unknown>>(`/users/${id}`, data),
  deleteUser: (id: string) => client.delete(`/users/${id}`),
  // 统计看板
  stats: () => client.get<AdminStatsData>("/admin/stats"),
  // 待审核知识点队列
  candidates: (params?: { status?: string; skip?: number; limit?: number }) =>
    client.get<CandidatesPublic>("/admin/candidates", { params }),
  submitCandidate: (data: CandidateCreate) =>
    client.post<CandidateKp>("/admin/candidates", data),
  editCandidate: (id: string, data: Partial<CandidateCreate>) =>
    client.patch<CandidateKp>(`/admin/candidates/${id}`, data),
  approveCandidate: (id: string) =>
    client.post<{ message: string }>(`/admin/candidates/${id}/approve`),
  rejectCandidate: (id: string) =>
    client.post<{ message: string }>(`/admin/candidates/${id}/reject`),
  batchApprove: (ids: string[]) =>
    client.post<{ approved: string[]; approved_count: number; failed: { id: string; name?: string; reason: string }[] }>(
      "/admin/candidates/batch-approve",
      { ids },
    ),
  batchReject: (ids: string[]) =>
    client.post<{ rejected_count: number }>("/admin/candidates/batch-reject", { ids }),
  // 系统日志
  logs: (params?: { skip?: number; limit?: number }) =>
    client.get<ExtractionLogsPublic>("/admin/logs", { params }),
  // 教师共建建议工单（knowledge_suggestion 表）
  suggestions: (params?: { status?: string; skip?: number; limit?: number }) =>
    client.get<{ data: CandidateKp[]; count: number }>("/admin/suggestions", { params }),
  submitSuggestion: (data: {
    kind: string
    name: string
    subject?: string
    grade_level?: string | null
    textbook_version?: string | null
    chapter?: string | null
    target_kp_id?: string | null
    definition?: string | null
    suggestion?: string | null
  }) => client.post("/admin/suggestions", data),
  approveSuggestion: (id: string) =>
    client.post<{ message: string }>(`/admin/suggestions/${id}/approve`),
  rejectSuggestion: (id: string) =>
    client.post<{ message: string }>(`/admin/suggestions/${id}/reject`),
  // 图谱质量检测
  graphQuality: () =>
    client.get<{
      cycles: { name_a: string; name_b: string; rel1: string; rel2: string }[]
      isolated_nodes: string[]
      key_points_without_dependencies: string[]
    }>("/admin/graph-quality"),
}

// ==================== AI 助手（SSE 流式） ====================

export async function* streamChat(
  message: string,
  history: { role: "user" | "assistant"; content: string }[],
): AsyncGenerator<{
  type: string
  content?: string
  tool_name?: string
  sources?: { type: string; name: string; id: string }[]
  reply?: string
}> {
  // SSE 用原生 fetch（需要流式读取），绕过了 axios 拦截器，
  // 用 authorizedFetch 对齐 401 语义：清 token 跳登录
  const resp = await authorizedFetch("/api/v1/chat/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, mode: "sse" }),
  })
  if (resp.status === 401) {
    throw new Error("登录已过期，请重新登录")
  }
  if (!resp.ok || !resp.body) {
    // 优先取后端 detail 字段（403 业务拒绝/500 等），给用户可读原因
    let detail = ""
    try {
      const data = await resp.json()
      detail = typeof data?.detail === "string" ? data.detail : ""
    } catch {
      // 非 JSON 响应体，忽略
    }
    throw new Error(detail || `请求失败 (${resp.status})`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith("data: ")) continue
      const payload = trimmed.slice(6)
      try {
        yield JSON.parse(payload)
      } catch {
        // 忽略无法解析的行
      }
    }
  }
}

// （管理员后台 API 见上方 adminApi）
