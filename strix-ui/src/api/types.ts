export interface UserOut {
  id: string;
  email: string;
  name: string;
  two_factor_enabled: boolean;
}

export interface OrganizationOut {
  id: string;
  name: string;
  created_at: string;
}

export interface MeOut {
  user: UserOut;
  active_org: OrganizationOut | null;
  role: string | null;
  organizations: OrganizationOut[];
}

export interface MembershipOut {
  id: string;
  org_id: string;
  role: string;
  user: UserOut;
}

export interface Repository {
  id: string;
  provider: string;
  full_name: string;
  default_branch: string;
  auto_review_enabled: boolean;
  last_tested_at: string | null;
  open_issues_count: number;
}

export type RepoRefType = "branches" | "tags" | "commits";

export interface RepoBranchOrTag {
  name: string;
  commit_sha: string;
}

export interface RepoCommit {
  sha: string;
  message: string;
  author_date: string | null;
}

export interface RepoPullRequest {
  number: number;
  title: string;
  author: string;
  source_branch: string | null;
  target_branch: string | null;
  url: string | null;
}

export interface InstallableRepo {
  full_name: string;
  default_branch: string;
  private: boolean;
}

export interface DomainOut {
  id: string;
  hostname: string;
  verified: boolean;
  verification_method: string;
  verification_token: string;
  last_tested_at: string | null;
}

export type PentestStatus = "queued" | "running" | "completed" | "failed" | "stopped";

export interface Pentest {
  id: string;
  org_id: string;
  target_type: "repository" | "domain";
  target_id: string;
  target_label: string;
  extra_domain_id: string | null;
  ref: string | null;
  resolved_commit_sha: string | null;
  scan_mode: string;
  skills: string[];
  status: PentestStatus;
  started_at: string | null;
  finished_at: string | null;
  severity_counts: Record<string, number>;
  llm_input_tokens: number;
  llm_output_tokens: number;
  llm_total_tokens: number;
  mock_fallback_reason: string | null;
  coverage: PentestCoverage | null;
  created_at: string;
}

export interface PentestCoverageGap {
  kind: string;
  surface: string;
  risk_area: string;
  detail: string;
}

export interface PentestCoverageAgent {
  agent_id: string;
  agent_name: string;
  status: string;
  skills: string[];
  is_root?: boolean;
}

export interface PentestCoverage {
  mode: "real" | "mock";
  finish_scan: boolean;
  complete: boolean;
  scan_status?: string | null;
  exit_reason?: string | null;
  caveats: string[];
  summary: Record<string, unknown>;
  gaps: PentestCoverageGap[];
  agents: PentestCoverageAgent[];
  recall?: ChecklistRecall;
}

export interface ChecklistRecallItem {
  id: string;
  title: string;
  severity: Severity;
  status: "hit" | "miss";
  matched_finding_titles: string[];
}

export interface ChecklistRecall {
  applicable: boolean;
  checklist_id: string;
  title: string;
  source: string;
  matched: number;
  missed: number;
  total: number;
  recall: number;
  items: ChecklistRecallItem[];
}

export interface PentestCompareIssue {
  id: string;
  title: string;
  severity: Severity;
  source: string | null;
  file_path: string | null;
  line_number: number | null;
  disposition: IssueDisposition;
}

export interface PentestCompare {
  previous_pentest_id: string | null;
  previous_status?: string;
  previous_finished_at?: string | null;
  still_open: PentestCompareIssue[];
  new: PentestCompareIssue[];
  gone: PentestCompareIssue[];
}

export interface StandardSkill {
  name: string;
  label: string;
  description: string;
}

export interface PentestSchedule {
  id: string;
  target_type: string;
  target_id: string;
  scan_mode: string;
  skills: string[];
  cron_expr: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

export type Severity = "critical" | "high" | "medium" | "low";
export type IssueStatus = "open" | "in_progress" | "snoozed" | "fixed" | "ignored";
export type IssueDisposition = "pending" | "confirmed" | "rejected" | "needs_repro" | "out_of_scope";

export interface Issue {
  id: string;
  org_id: string;
  pentest_id: string | null;
  pr_review_id: string | null;
  repository_id: string | null;
  domain_id: string | null;
  title: string;
  description: string;
  severity: Severity;
  status: IssueStatus;
  cvss: number | null;
  cvss_breakdown: Record<string, unknown>;
  technical_analysis: string;
  remediation_steps: string;
  poc_description: string;
  poc_script_code: string;
  code_before: string | null;
  code_after: string | null;
  target: string;
  endpoint: string;
  fix_effort: string;
  source: string | null;
  disposition: IssueDisposition;
  disposition_note: string | null;
  file_path: string | null;
  line_number: number | null;
  specialist_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface IssuesResponse {
  items: Issue[];
  severity_counts: Record<Severity, number>;
  status_counts: Record<string, number>;
}

export type PRReviewStatus = "running" | "awaiting_merge" | "needs_attention" | "merged_with_open_findings" | "passed" | "failed";

export interface PRReview {
  id: string;
  repository_id: string;
  repository_full_name: string;
  pr_number: number;
  title: string;
  author: string;
  status: PRReviewStatus;
  findings_count: number;
  target_branch: string | null;
  resolved_head_sha: string | null;
  error: string | null;
  llm_input_tokens: number;
  llm_output_tokens: number;
  llm_total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface PRReviewsResponse {
  items: PRReview[];
  counts: Record<string, number>;
}

export interface PRReviewSettings {
  rereview_on_push: boolean;
  target_branches: string[];
  approve_clean_prs: boolean;
  block_prs_on_findings: boolean;
  blocking_severities: Severity[];
  exclude_bot_accounts: boolean;
  excluded_usernames: string[];
  allow_overage_reviews: boolean;
  review_cap_per_dev: number | null;
  review_cap_period: string;
}

export interface KnowledgeEntry {
  id: string;
  type: string;
  description: string;
  scope_type: "global" | "repository" | "domain";
  scope_id: string | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  category: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatSuggestion {
  title: string;
  prompt: string;
}

export interface ApiToken {
  id: string;
  name: string;
  token_type: string;
  scopes: string[];
  token_prefix: string;
  status: string;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface LlmSettings {
  model: string;
  api_base: string | null;
  api_key_set: boolean;
  api_key_last4: string | null;
  updated_at: string;
}

export interface Webhook {
  id: string;
  url: string;
  events: string[];
  secret: string;
  status: string;
  created_at: string;
}

export interface Subscription {
  plan: string;
  status: string;
  trial_ends_at: string | null;
  card_added: boolean;
  current_period_end: string | null;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  actor_email: string;
  action: string;
  target: string;
  extra: Record<string, unknown>;
  created_at: string;
}

export interface RequestLogEntry {
  id: string;
  actor_email: string;
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PentestLogLine {
  ts: string;
  level: string;
  scan_id: string;
  agent_id: string;
  logger: string;
  message: string;
}

export interface PentestLogsResponse {
  available: boolean;
  lines: PentestLogLine[];
  total_lines: number;
  total_matched: number;
  agent_ids: string[];
  llm_usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface Integration {
  provider: string;
  category: "code" | "communication" | "issue_tracking";
  label: string;
  coming_soon: boolean;
  live: boolean;
  configure_url: string | null;
  status: "connected" | "not_connected";
  account_label: string | null;
  base_url: string | null;
  credential_last4: string | null;
  connected_at: string | null;
}
