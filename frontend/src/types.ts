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
  classroom_exercises?: ClassroomExercise[]
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

// ==================== 作业 / 提交 ====================

export type QuestionType = "choice" | "fill" | "short" | "essay"
export type HomeworkStatus = "draft" | "published" | "closed"
export type SubmissionStatus = "submitted" | "graded"

/** 教案课堂习题（一键生成作业的初始题目来源） */
export interface ClassroomExercise {
  id: string
  type: QuestionType
  stem: string
  options?: string[]
  correct_option?: number | null
  answers?: string[]
  reference_answer?: string
}

/** 作业单题：每题必选 ≥1 关联知识点；填空 answers 支持多解 */
export interface HomeworkQuestion {
  id: string
  type: QuestionType
  stem: string
  knowledge_point_ids: string[]
  options: string[]
  correct_option: number | null
  answers: string[]
  reference_answer: string
  score?: number
}

export interface Homework {
  id: string
  title: string
  lesson_plan_id?: string | null
  owner_id: string
  org_id?: string | null
  status: HomeworkStatus
  knowledge_point_ids: string[]
  knowledge_points: KnowledgePoint[]
  questions: HomeworkQuestion[]
  created_at?: string | null
  updated_at?: string | null
}

export interface HomeworksPublic {
  data: Homework[]
  count: number
}

export interface HomeworkUpdatePayload {
  title?: string
  knowledge_point_ids?: string[]
  questions?: HomeworkQuestion[]
}

export interface Submission {
  id: string
  homework_id: string
  student_id_hash: string
  answers: { question_id: string; content: any }[]
  status: SubmissionStatus
  // PRD §7④：True=已被该学生的后续提交覆盖（保留留痕，不物理删除）
  superseded?: boolean
  submitted_at?: string | null
  created_at?: string | null
}

export interface SubmissionsPublic {
  data: Submission[]
  count: number
}

export interface SimulateSubmitRequest {
  student_id: string
  answers: { question_id: string; content: any }[]
}

// ==================== 判分 / 批改（FR-04/05/06） ====================

export type QuestionGradeStatus = "pending" | "auto_graded" | "finalized"

/** 单题判分记录：客观题自动判分结果 / 主观题 AI 建议 / 教师终评 */
export interface QuestionGrade {
  id: string
  submission_id: string
  question_id: string
  question_type: QuestionType
  full_score: number
  // 客观题（FR-04）
  is_correct?: boolean | null
  auto_score?: number | null
  auto_detail?: string | null
  // 主观题 AI 建议（FR-05）
  ai_suggested_score?: number | null
  ai_comment?: string | null
  ai_knowledge_points: string[]
  ai_confidence?: number | null
  needs_human: boolean
  // PRD §7① AI 调用失败时的显式标记（True=AI 不可用，转人工）
  ai_unavailable?: boolean
  // 教师终评（FR-06）
  final_score?: number | null
  final_comment?: string | null
  finalized: boolean
  finalized_at?: string | null
  status: QuestionGradeStatus
}

export interface SubmissionGradesPublic {
  data: QuestionGrade[]
  count: number
  submission_status?: string | null
}

export interface FinalizeGradeRequest {
  final_score?: number | null
  final_comment?: string | null
  adopt_suggestion?: boolean
  confirm?: boolean
}

export interface GradeTriggerResponse {
  submission_id: string
  graded_count: number
  grades: QuestionGrade[]
  message?: string
}

/** FR-04 标注集验收报告 */
export interface LabeledSetReport {
  total: number
  correct: number
  accuracy: number
  threshold: number
  passed: boolean
  misjudged: {
    index: number
    tag: string
    question_id: string
    content: any
    expected: any
    got: any
    detail: string
  }[]
}

// ==================== 错误聚合看板（FR-07/08/09） ====================

export type ErrorStatScope = "class" | "personal"

/** 高频错误模式：一种错误表述及其出现次数 */
export interface ErrorPattern {
  expression: string
  count: number
  question_ids: string[]
}

/** 单个关联知识点的错误聚合结果 */
export interface KnowledgePointErrorStat {
  knowledge_point_id: string
  knowledge_point_name?: string | null
  question_count: number
  graded_count: number
  wrong_count: number
  error_rate: number
  top_patterns: ErrorPattern[]
}

export interface ErrorDashboard {
  homework_id: string
  homework_title?: string
  scope: ErrorStatScope
  submission_id?: string | null
  total_submissions: number
  graded_submissions: number
  knowledge_points: KnowledgePointErrorStat[]
  knowledge_point_total: number
}

/** FR-08 误区回流建议卡片 */
export interface MisconceptionSuggestion {
  knowledge_point_id: string
  knowledge_point_name?: string | null
  error_rate: number
  wrong_count: number
  graded_count: number
  threshold: number
  typical_expressions: string[]
  suggested_content: string
  suggested_correction: string
}

export interface MisconceptionSuggestions {
  data: MisconceptionSuggestion[]
  count: number
  threshold: number
}

export interface BackflowConfirmRequest {
  knowledge_point_id: string
  content: string
  correction?: string
}

export interface MisconceptionOut {
  id: string
  content: string
  correction: string
  source: string
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
  review_note?: string | null
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
