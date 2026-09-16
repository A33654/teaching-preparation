// ==================== 通用 ====================

export interface Message {
  message: string
}

export interface UserPublic {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  full_name?: string | null
  nickname?: string | null
  bio?: string | null
  phone?: string | null
  avatar_url?: string | null
  subject?: string | null
  grade_level?: string | null
  school?: string | null
  created_at?: string | null
}

export interface UserUpdateMe {
  full_name?: string | null
  email?: string | null
  nickname?: string | null
  bio?: string | null
  phone?: string | null
  avatar_url?: string | null
  subject?: string | null
  grade_level?: string | null
  school?: string | null
}

export interface UsersPublic {
  data: UserPublic[]
  count: number
}

// ==================== 知识图谱（Neo4j） ====================

export type RelationType = "prerequisite" | "contains" | "related_to"

export interface KnowledgePoint {
  id: string
  name: string
  subject: string
  description?: string | null
  grade_level?: string | null
  difficulty: number
  is_key_point: boolean
  owner_id?: string | null
  created_at?: string | null
}

export interface KnowledgePointsPublic {
  data: KnowledgePoint[]
  count: number
}

export interface KnowledgeRelation {
  source_id: string
  target_id: string
  relation_type: RelationType
}

export interface GraphData {
  nodes: KnowledgePoint[]
  edges: KnowledgeRelation[]
}

// ==================== 文档 ====================

export type DocumentStatus = "uploaded" | "parsing" | "analyzing" | "completed" | "failed"

export interface DocumentItem {
  id: string
  filename: string
  original_filename: string
  file_type: string
  file_size: number
  status: DocumentStatus
  error_message?: string | null
  created_at?: string | null
  owner_id: string
  extracted_text?: string | null
  summary?: string | null
  subject_id?: string | null
  knowledge_point_ids: string[]
  knowledge_points: KnowledgePoint[]
}

export interface DocumentsPublic {
  data: DocumentItem[]
  count: number
}

export interface ExtractionResult {
  subject: string
  knowledge_points_count: number
  relations_count: number
  knowledge_points: { id: string; name: string; subject: string }[]
  relations: KnowledgeRelation[]
  summary: string
}

// ==================== 教案 ====================

export interface LessonPlan {
  id: string
  title: string
  subject: string
  grade_level?: string | null
  teaching_objectives?: string | null
  teaching_process?: string | null
  owner_id: string
  subject_id?: string | null
  created_at?: string | null
  knowledge_point_ids: string[]
  knowledge_points: KnowledgePoint[]
  verification_report?: {
    missing_kps: string[]
    missing_exam_points: string[]
    missing_prereqs: string[]
    order_issues: string[]
    passed: boolean
    checked_count: number
  } | null
}

export interface LessonPlansPublic {
  data: LessonPlan[]
  count: number
}

export interface AiGenerateRequest {
  knowledge_point_ids: string[]
  subject: string
  grade_level: string
  extra_context: string
  style: string
  requirements: string
  summary_text: string
  chapter?: string // 章节名称：提供时后端自动联动图谱知识点，无需手动选择
}

export interface AiGenerateResponse {
  id: string
  title: string
  subject: string
  grade_level: string
  teaching_objectives: string
  teaching_process: string
  key_points: string[]
  difficult_points: string[]
  graph_context: Record<string, any>[]
  raw_text: string
}

export interface SummarizeResult {
  summary: string
  key_topics: string[]
  suggested_approach: string
}

// ==================== AI 助手（SSE） ====================

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

export interface ChatEvent {
  type: "token" | "tool_result" | "done" | "error"
  content?: string
  tool_name?: string
  sources?: { type: string; name: string; id: string }[]
  reply?: string
}

// ==================== 学科/教材/章节 ====================

export interface Subject {
  id: string
  name: string
  description?: string | null
  created_at?: string | null
  owner_id: string
}

export interface Textbook {
  id: string
  name: string
  version?: string | null
  grade_level?: string | null
  cover_url?: string | null
  description?: string | null
  subject_id: string
  created_at?: string | null
  owner_id: string
}

export interface Chapter {
  id: string
  title: string
  order_index: number
  level: number
  parent_id?: string | null
  textbook_id: string
  knowledge_point_id?: string | null
  created_at?: string | null
  children: Chapter[]
}

// ==================== 课程表/任务 ====================

export interface Schedule {
  id: string
  day_of_week: number // 0=周一
  start_time: string
  end_time: string
  subject: string
  classroom: string
  created_at?: string | null
  owner_id: string
}

export interface TaskItem {
  id: string
  title: string
  description: string
  due_date: string
  priority: string
  completed: boolean
  created_at?: string | null
  owner_id: string
}

export interface TodayOverview {
  today_schedule: Schedule[]
  upcoming_tasks: TaskItem[]
  day_name: string
}

// ==================== PPT ====================

export interface PptRecord {
  id: string
  title: string
  original_filename: string
  file_size: number
  slide_count: number
  extracted_text?: string | null
  slides_json?: string | null
  style?: string | null
  created_at?: string | null
  owner_id: string
  subject_id?: string | null
}

export interface PptRecordsPublic {
  data: PptRecord[]
  count: number
}

export interface SlideContent {
  title: string
  bullets: string[]
}

// ==================== 仪表盘 ====================

export interface SubjectDashboard {
  subject: Subject
  documents: DocumentItem[]
  lesson_plans: LessonPlan[]
  ppts: PptRecord[]
  knowledge_points: KnowledgePoint[]
}

// ==================== 管理员后台 ====================

export type CandidateStatus = "pending" | "approved" | "rejected"

export interface CandidateKp {
  id: string
  name: string
  subject: string
  grade_level?: string | null
  textbook_version?: string | null
  definition?: string | null
  prerequisites?: string | null
  source: string // llm_extraction | teacher_submit
  status: CandidateStatus
  document_id?: string | null
  submitter_id: string
  created_at?: string | null
  kind?: string | null
  target_kp_id?: string | null
  suggestion?: string | null
}

export interface CandidatesPublic {
  data: CandidateKp[]
  count: number
}

export interface AdminStatsData {
  pending_candidates: number
  subjects_count: number
  knowledge_points_count: number
  documents_total: number
  documents_processing: number
  documents_failed: number
}

export interface ExtractionLogItem {
  id: string
  task_type: string
  status: string
  message: string
  created_at?: string | null
}

export interface ExtractionLogsPublic {
  data: ExtractionLogItem[]
  count: number
}

export interface CandidateCreate {
  name: string
  subject?: string
  grade_level?: string | null
  textbook_version?: string | null
  definition?: string | null
  prerequisites?: string | null
  kind?: string | null // teacher_missing_kp | teacher_correction | teacher_misconception | teacher_exam_point
  target_kp_id?: string | null
  suggestion?: string | null
}
