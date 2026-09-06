import {useCallback, useEffect, useRef, useState} from 'react'
import {LoaderCircle, RefreshCw, RotateCcw, ShieldCheck} from 'lucide-react'
import {api, dateLabel, statusLabel} from './api'
import type {CatalogueModel, ModelCatalogue, ModelRole, ReasoningEffort, RoleModel, TaskModels} from './types'

export const modelRoles: {id: ModelRole; title: string; description: string}[] = [
  {id: 'extraction', title: 'Search and extraction', description: 'Identify candidate companies and extract observations from supplied notes. Your self-hosted SearXNG service performs the searches.'},
  {id: 'research', title: 'Research and account chat', description: 'Assess fit, draft account briefs, make corrections and answer questions about saved evidence.'},
  {id: 'review', title: 'Final evidence review', description: 'Independently check every proposed brief and chat answer against its original sources.'},
]

export const tokenPrice = (value: string) => '$' + new Intl.NumberFormat('en-US', {maximumFractionDigits: 6}).format(Number(value) * 1_000_000)

export function nextModelConfig(current: RoleModel, selected: CatalogueModel, role: ModelRole): RoleModel {
  const efforts = selected.roles[role].supported_efforts
  const effort = current.reasoning_effort !== null && efforts.includes(current.reasoning_effort)
    ? current.reasoning_effort
    : efforts.find(value => value === selected.reasoning.default_effort) ?? efforts[0] ?? null
  return {model: selected.id, reasoning_effort: effort}
}

export function ModelSettings({value, defaults, disabled, onChange, onValidity}: {
  value: TaskModels; defaults: TaskModels; disabled: boolean;
  onChange: (value: TaskModels) => void; onValidity: (valid: boolean) => void;
}) {
  const [catalogue, setCatalogue] = useState<ModelCatalogue | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [restored, setRestored] = useState(false)
  const request = useRef<AbortController | null>(null)
  const load = useCallback(async (refresh = false) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLoading(true); setError('')
    try {
      const next = await api<ModelCatalogue>('/models' + (refresh ? '?refresh=true' : ''), {signal: controller.signal})
      if (!controller.signal.aborted) setCatalogue(next)
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Could not load models. Try refreshing the list.')
    } finally { if (!controller.signal.aborted) setLoading(false) }
  }, [])
  useEffect(() => {void load(); return () => request.current?.abort()}, [load])
  const valid = !loading && !error && !!catalogue && modelRoles.every(({id}) => {
    const model = catalogue.models.find(item => item.id === value[id].model)
    return model?.roles[id].compatible && (value[id].reasoning_effort === null || model.roles[id].supported_efforts.includes(value[id].reasoning_effort!))
  })
  useEffect(() => onValidity(valid), [valid, onValidity])

  return <div className="task-model-settings">
    <div className="model-toolbar">
      <p><ShieldCheck size={16} />Zero-data-retention endpoints for every task</p>
      <div>
        <button className="button" type="button" disabled={loading || disabled} onClick={() => load(true)}>
          {loading ? <LoaderCircle size={14} className="spin" /> : <RefreshCw size={14} />}Refresh model list
        </button>
        <button className="text-button" type="button" disabled={disabled} onClick={() => {onChange(structuredClone(defaults)); setRestored(true)}}><RotateCcw size={14} />Restore defaults</button>
      </div>
    </div>
    {loading && <p className="model-feedback" role="status">Checking models, endpoint capabilities and current prices…</p>}
    {error && <p className="inline-error" role="alert">{error} Your selections have been kept.</p>}
    {restored && <p className="model-feedback" role="status">Default models selected.</p>}
    {modelRoles.map(role => <RoleEditor key={role.id} role={role} value={value[role.id]} models={catalogue?.models ?? []} loaded={!!catalogue} disabled={disabled || loading}
      onChange={config => {setRestored(false); onChange({...value, [role.id]: config})}} />)}
    <p className="model-price-note">Prices per 1 million tokens from eligible providers. Context tiers, provider availability and promotions can change the rate. Reasoning tokens count as output.
      {catalogue && <span>Checked {dateLabel(catalogue.fetched_at)} at {new Date(catalogue.fetched_at).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'})}.</span>}
    </p>
  </div>
}

function RoleEditor({role, value, models, loaded, disabled, onChange}: {
  role: typeof modelRoles[number]; value: RoleModel; models: CatalogueModel[]; loaded: boolean; disabled: boolean; onChange: (value: RoleModel) => void;
}) {
  const [query, setQuery] = useState('')
  const selected = models.find(item => item.id === value.model)
  const matches = models.filter(item => (item.id + ' ' + item.name).toLowerCase().includes(query.toLowerCase().trim()))
  const options = selected && !matches.includes(selected) ? [selected, ...matches] : matches
  const compatibility = selected?.roles[role.id]
  const efforts = compatibility?.supported_efforts ?? []
  const eligiblePrices = compatibility?.prices.filter(endpoint => value.reasoning_effort === null || endpoint.supported_efforts.includes(value.reasoning_effort)) ?? []
  const price = eligiblePrices[0]
  const unavailable = query.trim() ? matches.filter(item => !item.roles[role.id].compatible).slice(0, 3) : []
  return <section className="model-role" aria-labelledby={role.id + '-heading'}>
    <div className="model-role-intro"><h3 id={role.id + '-heading'}>{role.title}</h3><p>{role.description}</p></div>
    <div className="model-role-controls">
      <div>
        <label htmlFor={role.id + '-search'}>Find a model<input id={role.id + '-search'} type="search" aria-label={'Search ' + role.id + ' models'} value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name or model ID" disabled={disabled} /></label>
        <label htmlFor={role.id + '-model'}>Model<select id={role.id + '-model'} aria-label={role.title + ' model'} value={value.model} disabled={disabled || !loaded} onChange={event => {
          const next = models.find(item => item.id === event.target.value)
          if (next?.roles[role.id].compatible) onChange(nextModelConfig(value, next, role.id))
        }}>
          {!selected && <option value={value.model}>{value.model}{loaded ? ' — unavailable' : ''}</option>}
          {options.map(item => <option key={item.id} value={item.id} disabled={!item.roles[role.id].compatible}>{item.name} · {item.id}{item.roles[role.id].compatible ? '' : ' — unavailable'}</option>)}
        </select></label>
        {loaded && !compatibility?.compatible && <p className="inline-error">{compatibility?.reason ?? 'This saved model is not in the current catalogue.'}</p>}
        {query && !matches.length && <p className="model-feedback" role="status">No models match this search. Your current selection is retained.</p>}
        {unavailable.length > 0 && <ul className="model-unavailable" aria-label="Unavailable search results">{unavailable.map(item => <li key={item.id}><strong>{item.name}:</strong> {item.roles[role.id].reason}</li>)}</ul>}
      </div>
      <label htmlFor={role.id + '-effort'}>Reasoning effort<select id={role.id + '-effort'} aria-label={role.title + ' reasoning effort'} value={value.reasoning_effort ?? ''} disabled={disabled || !efforts.length} onChange={event => onChange({...value, reasoning_effort: (event.target.value || null) as ReasoningEffort | null})}>
        {(value.reasoning_effort === null || !efforts.length) && <option value="">Model default{selected?.reasoning.default_effort ? ` (${selected.reasoning.default_effort})` : ''}</option>}
        {value.reasoning_effort !== null && !efforts.includes(value.reasoning_effort) && <option value={value.reasoning_effort} disabled>{statusLabel(value.reasoning_effort)} — unavailable</option>}
        {efforts.map(effort => <option key={effort} value={effort}>{statusLabel(effort)}</option>)}
      </select><span className="field-hint">{selected?.reasoning.mandatory ? 'Reasoning is required. Higher effort can take longer and use more tokens.' : 'Only supported effort levels are offered.'}</span></label>
    </div>
    {price && <div className="model-rate"><strong>From {tokenPrice(price.pricing.prompt)} input / {tokenPrice(price.pricing.completion)} output</strong><span>per 1M tokens · {price.provider} · {eligiblePrices.length} eligible endpoint{eligiblePrices.length === 1 ? '' : 's'}</span>
      {!!price.pricing.overrides?.length && <span>Higher context tiers: {price.pricing.overrides.map(tier => `${tier.min_prompt_tokens.toLocaleString()}+ input tokens: ${tokenPrice(tier.prompt ?? price.pricing.prompt)} / ${tokenPrice(tier.completion ?? price.pricing.completion)}`).join('; ')} per 1M.</span>}
    </div>}
  </section>
}
