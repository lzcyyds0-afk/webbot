// ── Project ──
export interface Project {
  id: number;
  name: string;
  base_url: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  base_url: string;
}

// ── TestCase ──
export interface StepDef {
  action: string;
  [key: string]: unknown;
}

export interface TestCase {
  id: number;
  project_id: number;
  name: string;
  steps_json: StepDef[];
  cookies_json?: Array<{
    name: string;
    value: string;
    domain: string;
    path?: string;
    expires?: number;
    httpOnly?: boolean;
    secure?: boolean;
    sameSite?: 'Strict' | 'Lax' | 'None';
  }> | null;
  auth_json?: {
    local_storage?: Record<string, string>;
    session_storage?: Record<string, string>;
    credentials?: {
      url?: string;
      username?: string;
      password_encrypted?: string;
      username_selector?: string;
      password_selector?: string;
      submit_selector?: string;
      success_url_pattern?: string;
    };
  } | null;
  created_at: string;
  updated_at: string;
}

export interface TestCaseCreate {
  name: string;
  steps_json?: StepDef[];
}

// ── Run ──
export type RunStatus = 'pending' | 'running' | 'passed' | 'failed';

export interface RunNarrative {
  summary: string;
  process: string;
  conclusion: string;
}

export interface Run {
  id: number;
  test_case_id: number;
  project_id: number | null;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  narrative: RunNarrative | null;
}

export interface RunCreate {
  test_case_id: number;
}

// ── RunStep ──
export type StepStatus = 'pending' | 'running' | 'passed' | 'failed';

export interface RunStep {
  id: number;
  run_id: number;
  step_index: number;
  action: string;
  input_json: Record<string, unknown> | null;
  output_json: Record<string, unknown> | null;
  screenshot_path: string | null;
  status: StepStatus;
  duration_ms: number | null;
  error: string | null;
  params_summary?: string | null;
}

// ── Step Details ──
export interface ConsoleLog {
  type: string;
  text: string;
  location?: Record<string, unknown>;
}

export interface NetworkRequest {
  url: string;
  method: string;
  resource_type: string;
  headers: Record<string, string>;
  response?: {
    status: number;
    status_text: string;
    headers: Record<string, string>;
  };
}

export interface StepDetails {
  console_logs: ConsoleLog[];
  network_requests: NetworkRequest[];
  dom_snippet: string | null;
  target_bbox: { x: number; y: number; width: number; height: number } | null;
}

// ── LLMConfig ──
export type LLMProvider = 'openai' | 'anthropic' | 'gemini' | 'ollama';

export interface LLMConfig {
  id: number;
  name: string;
  provider: LLMProvider;
  model: string;
  api_key_encrypted: string;
  base_url: string | null;
  params_json: Record<string, unknown> | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface LLMConfigCreate {
  name: string;
  provider: LLMProvider;
  model: string;
  api_key: string;
  base_url?: string;
  params_json?: Record<string, unknown>;
  is_default?: boolean;
}

export interface LLMConfigUpdate extends Partial<LLMConfigCreate> {}

export interface LLMTestRequest {
  config_id: number;
  prompt: string;
}

export interface LLMTestResponse {
  content: string;
  usage: Record<string, unknown>;
  model: string;
  success: boolean;
  error: string | null;
}

// ── Step Diagnosis ──
export interface DiagnosisSummary {
  action: string;
  error_text: string;
  error_type: string;
  selector: string | null;
  step_index: number;
}

export interface DiagnosisContext {
  screenshot_url: string;
  dom_exists: boolean;
  dom_visible: boolean;
  dom_obscured: boolean;
  viewport_info: { width: number; height: number; scroll_x: number; scroll_y: number };
  page_url: string;
  page_title: string;
  expected_url: string | null;
}

export interface DiagnosisVisualDiff {
  has_baseline: boolean;
  baseline_run_id: number | null;
  baseline_screenshot_url: string | null;
  baseline_run_started_at: string | null;
  current_screenshot_url: string;
  diff_note: string;
}

export interface CandidateSelector {
  selector: string;
  confidence: number;
  reason: string;
  found_count: number;
}

export interface DiagnosisFixes {
  candidate_selectors: CandidateSelector[];
  suggest_wait: boolean;
  suggest_scroll: boolean;
  suggest_retry: boolean;
}

export interface DiagnosisPayload {
  summary: DiagnosisSummary;
  context: DiagnosisContext;
  visual_diff: DiagnosisVisualDiff;
  fixes: DiagnosisFixes;
  ai_diagnosis?: AiDiagnosis;
  generated_at: string;
}

export interface StepDiagnosis {
  id: number;
  run_id: number;
  step_index: number;
  payload_json: DiagnosisPayload;
  created_at: string;
}

// ── AI Diagnosis ──
export interface PatchOp {
  op: 'replace' | 'insert' | 'delete';
  step_index: number;
  step?: StepDef;
}

export interface AiSuggestedFix {
  type: string;
  new_steps_patch: PatchOp[];
}

export interface AiDiagnosis {
  root_cause: string;
  explanation: string;
  suggested_fix: AiSuggestedFix;
  confidence: number;
}

// ── Project Report ──
export interface ProjectReportKpi {
  total_runs: number;
  pass_rate: number;
  avg_duration_ms: number | null;
  failed_cases: number;
}

export interface ProjectReportTrendPoint {
  date: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
}

export interface ProjectReportDurationByAction {
  action: string;
  count: number;
  p50: number;
  p95: number;
}

export interface ProjectReportFailedStepTop {
  action: string;
  selector: string;
  failure_count: number;
  last_failed_at: string | null;
  last_run_id: number;
  last_run_step_index: number;
}

export interface ProjectReportActionSuccessRate {
  action: string;
  total: number;
  passed: number;
  failed: number;
  rate: number;
}

export interface ProjectReportAiConfidence {
  bins: number[];
  counts: number[];
  avg: number | null;
}

export interface ProjectReport {
  kpi: ProjectReportKpi;
  trend: ProjectReportTrendPoint[];
  duration_by_action: ProjectReportDurationByAction[];
  failed_steps_top: ProjectReportFailedStepTop[];
  action_success_rate: ProjectReportActionSuccessRate[];
  ai_confidence: ProjectReportAiConfidence;
}

// ── AI Scout ──
export interface ScoutPath {
  title: string;
  description: string;
  steps: StepDef[];
  risk_level: number;
  tags: string[];
}

export interface ScoutResponse {
  url: string;
  page_title: string;
  screenshot_b64: string | null;
  elements_count: number;
  paths: ScoutPath[];
  raw_llm_output: string | null;
  retry_used: boolean;
}

// ── AI Explain (Preview) ──
export interface StepExplanation {
  step_index: number;
  action: string;
  intent: string;
  prediction: string;
  risk: string;
  risk_level: 'low' | 'medium' | 'high';
  confidence: number;
}

export interface TestCaseExplainOut {
  case_id: number;
  overall_risk: 'low' | 'medium' | 'high';
  overall_advice: string;
  steps: StepExplanation[];
}

// ── WebSocket Messages ──
export interface WsMessage {
  event: 'step_start' | 'step_end' | 'run_end' | 'step_update' | 'heal_notice';
  run_id: number;
  step_index: number | null;
  status: string;
  screenshot_url?: string | null;
  error?: string | null;
  timestamp?: string;
  // enriched fields
  action?: string | null;
  params_summary?: string | null;
  duration_ms?: number | null;
  screenshot_before?: string | null;
  screenshot_after?: string | null;
  dom_snippet?: string | null;
  target_bbox?: { x: number; y: number; width: number; height: number } | null;
  console_logs?: ConsoleLog[] | null;
  network_requests?: NetworkRequest[] | null;
  // heal fields
  healed?: boolean;
  healed_selector?: string | null;
  heal_method?: string | null;
  original_selector?: string | null;
}
