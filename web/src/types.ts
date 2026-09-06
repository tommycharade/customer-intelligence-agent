export type Profile = {
  offering: string; company_type: string; technology: string; buyer_role: string;
  problem: string; buying_trigger: string; exclusions: string[]; geography: string; trigger_days: number;
}
export type Settings = {
  model: string; model_budget: number; search_budget: number; candidate_limit: number;
  allowed_domains: string[]; blocked_domains: string[]; browser_fallback: boolean;
}
export type SourceType = 'website' | 'documentation' | 'job' | 'discussion' | 'inbound' | 'interview' | 'asset' | 'exclusion' | 'other'
export type Source = {
  id: string; title: string; text: string; source_type: SourceType; origin: 'public' | 'upload' | 'demo';
  url: string | null; account_domain: string | null; published_at: string | null;
  retrieved_at: string; content_hash: string; is_demo: boolean; characters?: number;
}
export type Evidence = {source_id: string; quote: string}
export type Claim = {text: string; kind: 'fact' | 'hypothesis'; evidence: Evidence[]; reasoning: string | null; event_date: string | null}
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
export type Costs = {model_usd: number; search_credits: number; has_estimates: boolean}
export type Run = {
  id: string; created_at: string; completed_at: string | null; is_demo: boolean; status: string;
  stage: string; profile: Profile; settings: Settings; candidate_count: number; processed: number;
  account_ids: string[]; error: string | null; costs: Costs;
  input_review: {observations: string[]; hypotheses: string[]};
}
export type Bootstrap = {
  profile: Profile | null; settings: Settings; data_directory: string;
  credentials: Record<string, {configured: boolean; environment: boolean}>;
}
export type Chat = {id: string; account_id: string; at: string; question: string; answer: string; evidence: Evidence[]}
export type Cohort = {week: string; recommended: number; contacted: number; relevant: number; uncontacted: number; rejected: number; conversion: number}
export type RunEvent = {id: string; run_id: string; at: string; message: string; url?: string}
