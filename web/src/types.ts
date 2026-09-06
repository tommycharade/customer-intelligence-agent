export type Profile = {
  offering: string; company_type: string; technology: string; buyer_role: string;
  problem: string; buying_trigger: string; exclusions: string[]; geography: string; trigger_days: number;
}
export type ModelRole = 'extraction' | 'research' | 'review'
export type ReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max'
export type RoleModel = {model: string; reasoning_effort: ReasoningEffort | null}
export type TaskModels = Record<ModelRole, RoleModel>
export type EndpointPrice = {provider: string; tag: string; structured_outputs: boolean; supported_efforts: ReasoningEffort[]; pricing: {prompt: string; completion: string; overrides?: {min_prompt_tokens: number; prompt?: string; completion?: string}[]}}
export type CatalogueModel = {
  id: string; name: string;
  roles: Record<ModelRole, {compatible: boolean; reason: string | null; endpoint_count: number; supported_efforts: ReasoningEffort[]; prices: EndpointPrice[]}>;
  reasoning: {supported_efforts: ReasoningEffort[]; mandatory: boolean; default_effort: ReasoningEffort | null};
}
export type ModelCatalogue = {models: CatalogueModel[]; fetched_at: string}
export type Settings = {
  models: TaskModels; model_budget: number; max_search_queries: number; max_pages_fetched: number; max_search_iterations: number; max_llm_iterations: number; candidate_limit: number;
  allowed_domains: string[]; blocked_domains: string[]; browser_fallback: boolean;
}
export type SourceType = 'website' | 'documentation' | 'job' | 'discussion' | 'inbound' | 'interview' | 'asset' | 'exclusion' | 'other'
export type Source = {
  id: string; title: string; text: string; source_type: SourceType; origin: 'public' | 'upload' | 'demo';
  url: string | null; account_domain: string | null; published_at: string | null;
  retrieved_at: string; content_hash: string; is_demo: boolean; characters?: number;
}
export type Evidence = {source_id: string; quote: string}
export type Claim = {text: string; kind: 'fact' | 'inference' | 'hypothesis'; evidence: Evidence[]; reasoning: string | null; event_date: string | null}
export type Stakeholder = {role: 'user' | 'champion' | 'budget_holder'; title: string; name: string | null; confidence: string; basis: Claim}
export type Brief = {
  company_name: string; domain: string; summary: string; fit: string;
  criteria: {criterion: string; status: string; evidence: Evidence[]}[]; matched_exclusions: string[];
  why_fits: Claim[]; why_now: Claim | null; who_matters: Stakeholder[];
  what_could_help: {kind: string; title: string; reason: string; asset_id: string | null}[];
}
export type OutcomeStatus = 'unreviewed' | 'shortlisted' | 'rejected' | 'contacted' | 'conversation' | 'relevant_conversation'
export type Account = {
  id: string; name: string; domain: string; brief: Brief; source_ids: string[];
  first_recommended_at: string; updated_at: string; run_id: string; is_demo: boolean;
  outcome: {status: OutcomeStatus; note: string; relevant_conversation_at?: string | null};
}
export type RoleCosts = {model_usd: number; calls: number; has_estimates: boolean}
export type Costs = {model_usd: number; search_credits: number; search_queries: number; pages_fetched: number; has_estimates: boolean; by_role?: Record<string, RoleCosts>}
export type ModelCall = {
  id: string; run_id: string; at: string; role: ModelRole; model: string; reasoning_effort: ReasoningEffort | null;
  purpose: string; status: string; provider: string | null; actual_model?: string | null;
  reserved_usd: number; actual_usd: number | null; usage: {prompt_tokens?: number; completion_tokens?: number; reasoning_tokens?: number};
  verdict: {supported: boolean; issues: string[]} | null;
}
export type Run = {
  id: string; created_at: string; completed_at: string | null; is_demo: boolean; status: string;
  stage: string; degraded?: boolean; profile: Profile; settings: Settings; candidate_count: number; processed: number;
  account_ids: string[]; error: string | null; costs: Costs;
  input_review: {observations: string[]; hypotheses: string[]};
}
export type Bootstrap = {
  profile: Profile | null; settings: Settings; model_defaults: TaskModels; data_directory: string; credential_storage: string; research_stack: {provider: string; paid_escalation: string};
  credentials: Record<string, {configured: boolean; environment: boolean}>;
}
export type Chat = {id: string; account_id: string; at: string; question: string; answer: string; evidence: Evidence[]}
export type Cohort = {week: string; recommended: number; contacted: number; relevant: number; uncontacted: number; rejected: number; conversion: number}
export type RunEvent = {id: string; run_id: string; at: string; message: string; url?: string}
