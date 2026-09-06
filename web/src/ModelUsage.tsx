import {useEffect, useState} from 'react'
import {api, statusLabel} from './api'
import {modelRoles} from './ModelSettings'
import type {ModelCall, Run} from './types'

const spend = (value: number) => '$' + value.toFixed(4)

export function ModelUsage({run}: {run: Run}) {
  const [open, setOpen] = useState(false)
  const [calls, setCalls] = useState<ModelCall[] | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const totalCalls = Object.values(run.costs.by_role ?? {}).reduce((sum, role) => sum + role.calls, 0)
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setError('')
    api<ModelCall[]>('/runs/' + run.id + '/model-calls', {signal: controller.signal}).then(data => {if (!controller.signal.aborted) setCalls(data)}).catch(failure => {
      if (!controller.signal.aborted) setError(failure.message)
    })
    return () => controller.abort()
  }, [open, run.id, run.costs.model_usd, run.status, totalCalls, retry])
  return <details className="model-usage" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Models and spending</summary>
    <p className="model-price-note">Model choices are fixed for this run and its account chat.{run.is_demo ? ' This demo has no model calls or charges.' : ''}</p>
    <div className="model-usage-roles">{modelRoles.map(role => {
      const config = run.settings.models[role.id]
      const costs = run.costs.by_role?.[role.id]
      return <div key={role.id}><strong>{role.title}</strong><span>{config.model}</span><span>{config.reasoning_effort ? statusLabel(config.reasoning_effort) + ' reasoning' : 'Model-default reasoning'}</span><span>{spend(costs?.model_usd ?? 0)} · {costs?.calls ?? 0} calls{costs?.has_estimates ? ' · includes estimates' : ''}</span></div>
    })}</div>
    {run.costs.by_role?.legacy && <p className="model-price-note">Earlier calls without role attribution: {spend(run.costs.by_role.legacy.model_usd)}.</p>}
    {error && <p className="inline-error">{error} <button type="button" className="text-button" onClick={() => setRetry(value => value + 1)}>Retry loading calls</button></p>}
    {!calls && !error && <p className="model-feedback" role="status">Loading model calls…</p>}
    {calls && !calls.length && <p className="model-feedback">No model calls recorded for this run.</p>}
    {!!calls?.length && <ol className="model-call-list">{calls.map(call => <li key={call.id}>
      <div><strong>{statusLabel(call.role)} · {call.purpose}</strong><span>{statusLabel(call.status)} · {spend(call.actual_usd ?? call.reserved_usd)}{call.actual_usd === null ? ' estimated' : ''}</span></div>
      <p>{call.model} · {call.reasoning_effort ?? 'model-default'} reasoning · Provider: {call.provider ?? 'not reported'}</p>
      {call.usage.prompt_tokens !== undefined && <p>{call.usage.prompt_tokens.toLocaleString()} input / {call.usage.completion_tokens?.toLocaleString() ?? 'unreported'} output tokens{call.usage.reasoning_tokens !== undefined ? ` · ${call.usage.reasoning_tokens.toLocaleString()} reasoning tokens included` : ''}</p>}
      {call.verdict && <p className={call.verdict.supported ? 'model-verdict' : 'inline-error'}>Evidence review: {call.verdict.supported ? 'supported' : 'not supported'}{call.verdict.issues.length ? ' — ' + call.verdict.issues.join(' ') : ''}</p>}
    </li>)}</ol>}
  </details>
}
