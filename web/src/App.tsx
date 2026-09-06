import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  ArrowRight, ArrowUpRight, BookOpen, Building2, Check, ChevronRight, CircleHelp, Clock3,
  Download, ExternalLink, FileText, FlaskConical, FolderOpen, LayoutGrid, Link2, LoaderCircle,
  MessageSquare, Play, Plus, RefreshCw, Search, Send, Settings2, ShieldCheck, SlidersHorizontal,
  Square, Target, Trash2, Upload, X,
} from 'lucide-react'
import { ModelSettings } from './ModelSettings'
import { ModelUsage } from './ModelUsage'
import { api, dateLabel, money, safeLink, send, statusLabel } from './api'
import type { Account, Bootstrap, Chat, Claim, Cohort, Evidence, OutcomeStatus, Profile, Run, RunEvent, Settings, Source, SourceType } from './types'

type Page = 'Accounts' | 'Customer profile' | 'Inputs & assets' | 'Research runs' | 'Outcomes' | 'Settings'
type Perform = (action: () => Promise<unknown>, success?: string) => Promise<boolean>
const pages: {name: Page; icon: typeof Building2}[] = [
  {name: 'Accounts', icon: Building2}, {name: 'Customer profile', icon: Target},
  {name: 'Inputs & assets', icon: FolderOpen}, {name: 'Research runs', icon: Play},
  {name: 'Outcomes', icon: MessageSquare}, {name: 'Settings', icon: Settings2},
]
const outcomeOptions: OutcomeStatus[] = ['unreviewed', 'shortlisted', 'rejected', 'contacted', 'conversation', 'relevant_conversation']
const emptyProfile: Profile = {offering: '', company_type: '', technology: '', buyer_role: '', problem: '', buying_trigger: '', exclusions: [], geography: '', trigger_days: 90}

function Button({children, className = '', ...props}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={'button ' + className} {...props}>{children}</button>
}

export default function App() {
  const [page, setPage] = useState<Page>('Accounts')
  const [demo, setDemo] = useState(false)
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [selected, setSelected] = useState('')
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [notice, setNotice] = useState<{text: string; error: boolean} | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [drawer, setDrawer] = useState<{source: Source | null; link: Evidence; error?: string} | null>(null)
  const originFocus = useRef<HTMLElement | null>(null)
  const evidenceRequest = useRef(0)
  const [mobileDrawer, setMobileDrawer] = useState(window.matchMedia('(max-width: 700px)').matches)
  useEffect(() => {
    const media = window.matchMedia('(max-width: 700px)')
    const update = () => setMobileDrawer(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  const refresh = useCallback(async () => {
    const [boot, accts, history, inputs, metrics] = await Promise.all([
      api<Bootstrap>('/bootstrap'), api<Account[]>('/accounts?demo=' + demo),
      api<Run[]>('/runs?demo=' + demo), api<Source[]>('/sources'), api<Cohort[]>('/metrics'),
    ])
    setBootstrap(boot); setAccounts(accts); setRuns(history); setSources(inputs); setCohorts(metrics)
    setSelected(current => accts.some(account => account.id === current) ? current : accts[0]?.id || '')
  }, [demo])

  useEffect(() => {
    setLoading(true)
    refresh().catch(error => setNotice({text: error.message, error: true})).finally(() => setLoading(false))
  }, [refresh])

  const perform: Perform = async (action, success) => {
    setWorking(true); setNotice(null)
    try { await action(); if (success) setNotice({text: success, error: false}); return true }
    catch (error) { setNotice({text: error instanceof Error ? error.message : 'Something went wrong. Please retry.', error: true}); return false }
    finally { setWorking(false) }
  }

  const activeRun = runs.find(run => run.status === 'running')
  useEffect(() => {
    if (!activeRun) return
    const stream = new EventSource('/api/runs/' + activeRun.id + '/events')
    const listener = (event: MessageEvent) => {
      const data = JSON.parse(event.data) as {run: Run; events: RunEvent[]}
      setRuns(current => current.map(run => run.id === data.run.id ? data.run : run))
      setEvents(data.events)
      api<Account[]>('/accounts?demo=' + demo).then(setAccounts).catch(() => {})
      if (data.run.status !== 'running') { stream.close(); refresh().catch(() => {}) }
    }
    stream.addEventListener('progress', listener as EventListener)
    return () => stream.close()
  }, [activeRun?.id, demo, refresh])

  useEffect(() => {
    if (!notice || notice.error) return
    const timer = window.setTimeout(() => setNotice(null), 5000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const closeDrawer = useCallback(() => {
    evidenceRequest.current += 1
    setDrawer(null)
    requestAnimationFrame(() => { if (originFocus.current?.isConnected) originFocus.current.focus() })
  }, [])
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') closeDrawer() }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [closeDrawer])

  const openEvidence = async (link: Evidence) => {
    const request = ++evidenceRequest.current
    originFocus.current = document.activeElement as HTMLElement
    setDrawer({source: null, link})
    try { const source = await api<Source>('/sources/' + link.source_id); if (request === evidenceRequest.current) setDrawer({source, link}) }
    catch (error) { if (request === evidenceRequest.current) setDrawer({source: null, link, error: (error as Error).message}) }
  }
  const navigate = (destination: Page) => { setPage(destination); if (destination === 'Research runs') refresh().catch(error => setNotice({text: error.message, error: true})); evidenceRequest.current += 1; setDrawer(null) }
  const startRun = (domain?: string) => perform(async () => {
    const run = await send<Run>('/runs', {target_domain: domain || null})
    setDemo(false); setPage('Research runs'); setRuns(current => [run, ...current]); setEvents([])
  })
  const exploreDemo = () => perform(async () => { await send('/demo'); setDemo(true); setPage('Accounts'); setFilter('') })

  if (!bootstrap) return <main className="boot"><LayoutGrid size={32} /><h1>Customer Intelligence</h1>{loading ? <p><LoaderCircle className="spin" size={17} /> Opening your local workspace…</p> : <><p role="alert">{notice?.text || 'Could not connect to the local service.'}</p><Button onClick={() => perform(refresh)}>Retry connection</Button></>}</main>

  const account = accounts.find(item => item.id === selected)
  const ready = !!bootstrap.profile && Object.values(bootstrap.credentials).every(key => key.configured)
  const filtered = accounts.filter(item => (item.name + ' ' + item.domain + ' ' + item.brief.summary).toLowerCase().includes(filter.toLowerCase()))

  return <div className="app-shell">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <aside className="sidebar" inert={!!drawer && mobileDrawer}>
      <a href="#" className="brand" onClick={event => {event.preventDefault(); navigate('Accounts')}}><span className="brand-symbol"><LayoutGrid size={23} /></span><span>Customer<br /><strong>Intelligence</strong></span></a>
      <nav aria-label="Main navigation">{pages.map(({name, icon: Icon}) => <button key={name} className={page === name ? 'nav-item active' : 'nav-item'} aria-current={page === name ? 'page' : undefined} onClick={() => navigate(name)}><Icon size={18} /><span>{name}</span>{name === 'Accounts' && accounts.length > 0 && <span className="nav-count">{accounts.length}</span>}</button>)}</nav>
      <div className="sidebar-note"><BookOpen size={20} /><p>A small shortlist.<br />Clear evidence.<br /><strong>Better conversations.</strong></p></div>
      <div className="local-status"><span className="status-dot" /><div>On your Mac<small>Private local workspace</small></div></div>
    </aside>

    <div className="main-shell" inert={!!drawer && mobileDrawer}>
      <header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={13} /><span>{page}</span></div><div className="topbar-actions">{working && <LoaderCircle className="spin" size={15} />}<button className="quiet-button" onClick={() => demo ? setDemo(false) : exploreDemo()}><FlaskConical size={15} />{demo ? 'Exit demo' : 'Explore a demo'}</button><span className="user-avatar" aria-label="Single user workspace">CI</span></div></header>
      {demo && <div className="demo-banner"><FlaskConical size={17} /><span><strong>Synthetic demo.</strong> These examples are fictional. No API calls or charges.</span><button onClick={() => setDemo(false)}>Your workspace <ArrowRight size={15} /></button></div>}
      {notice && <div className={'notice ' + (notice.error ? 'error' : '')} role={notice.error ? 'alert' : 'status'}><span>{notice.text}</span><button className="icon-button" aria-label="Dismiss message" onClick={() => setNotice(null)}><X size={17} /></button></div>}

      <main id="workspace" tabIndex={-1}>
        {page === 'Accounts' && <>
          <div className="page-heading"><div><h1>Accounts worth your attention<span className="heading-dot">.</span></h1><p>Understand the fit. Inspect the evidence. Start a useful conversation.</p></div><Button className="primary" disabled={working || !!activeRun || !ready || demo} onClick={() => startRun()}><Plus size={17} /> Find accounts</Button></div>
          {!demo && !ready && accounts.length > 0 && <div className="setup-strip"><CircleHelp size={17} />Complete your profile and API settings to start research.<button onClick={() => navigate(!bootstrap.profile ? 'Customer profile' : 'Settings')}>Finish setup <ArrowRight size={15} /></button></div>}
          {activeRun && <button className="run-strip" onClick={() => navigate('Research runs')}><LoaderCircle className="spin" size={16} /><span>{activeRun.stage}</span><span>{money(activeRun.costs.model_usd)} of {money(activeRun.settings.model_budget)}</span><ArrowRight size={15} /></button>}
          {loading ? <div className="loading-line"><LoaderCircle className="spin" size={18} /> Loading accounts…</div> : accounts.length === 0 ? <div className="welcome-layout"><div className="welcome-copy"><div className="welcome-symbol"><Building2 size={35} strokeWidth={1.4} /></div><h2>Your next good conversation<br />starts with a better question.</h2><p>Tell the agent what a good customer looks like. It will research a small set of companies and explain why each one deserves your attention.</p><div className="welcome-actions"><Button className="primary" onClick={() => navigate(!bootstrap.profile ? 'Customer profile' : !ready ? 'Settings' : 'Inputs & assets')}>{!bootstrap.profile ? 'Set your customer profile' : !ready ? 'Connect research tools' : 'Add your context'}<ArrowRight size={16} /></Button><Button onClick={exploreDemo} disabled={working}>See an example</Button></div></div><div className="setup-list"><h3>A thoughtful first run</h3><SetupStep done={!!bootstrap.profile} title="Define a narrow customer profile" description="Company, technology, buyer, problem, trigger and exclusions." onClick={() => navigate('Customer profile')} /><SetupStep done={Object.values(bootstrap.credentials).every(key => key.configured)} title="Connect your research tools" description="OpenRouter for analysis. SearXNG and Crawl4AI for research." onClick={() => navigate('Settings')} /><SetupStep done={sources.some(source => source.origin === 'upload')} title="Bring your customer context" description="Selected enquiries, interview notes and useful assets. Optional." onClick={() => navigate('Inputs & assets')} /><p className="setup-footnote"><ShieldCheck size={15} />You choose when research starts. Your first run is capped at {money(bootstrap.settings.model_budget)} in model spending.</p></div></div> : <div className="review-workspace">
            <section className="account-list" aria-label="Ranked accounts"><div className="list-toolbar"><span>{accounts.length} accounts</span><span className="muted">Ranked by fit</span></div><label className="search-input"><Search size={16} /><input aria-label="Search accounts" placeholder="Find an account…" value={filter} onChange={event => setFilter(event.target.value)} /></label><div className="account-rows">{filtered.length === 0 ? <p className="empty-small">No accounts match that search.</p> : filtered.map((item, index) => <button key={item.id} className={'account-row ' + (selected === item.id ? 'selected' : '')} onClick={() => {setSelected(item.id); setDrawer(null)}} aria-pressed={selected === item.id}><div className="account-row-top"><span className="rank">{String(index + 1).padStart(2, '0')}</span><span className="company-monogram">{item.name.split(' ').map(word => word[0]).slice(0, 2).join('')}</span><div><h3>{item.name}</h3><span className="domain">{item.domain}</span></div><ChevronRight className="row-arrow" size={15} /></div><p>{item.brief.summary}</p><div className="account-row-meta"><span className={'fit-label ' + item.brief.fit}><span className="status-dot" />{statusLabel(item.brief.fit)} fit</span><span><Clock3 size={12} />{item.brief.why_now ? 'Timing signal' : 'Timing unknown'}</span></div>{item.outcome.status !== 'unreviewed' && <span className="outcome-pill">{statusLabel(item.outcome.status)}</span>}</button>)}</div><div className="list-footer"><ShieldCheck size={14} /><span>Evidence earns a place here.</span></div></section>
            {account && <AccountDetail key={account.id} account={account} disabled={working} onEvidence={openEvidence} perform={perform} onRefresh={() => startRun(account.domain)} onOutcome={async (status, note) => {await send('/accounts/' + account.id + '/outcome', {status, note}, 'PUT'); await refresh()}} />}
          </div>}
        </>}

        {page === 'Customer profile' && <ProfilePage profile={bootstrap.profile} disabled={working} onSave={value => perform(async () => {await send('/profile', value, 'PUT'); await refresh()}, 'Customer profile saved. Future runs will use these criteria.')} />}
        {page === 'Inputs & assets' && <InputsPage sources={sources} disabled={working} perform={perform} refresh={refresh} onEvidence={openEvidence} />}
        {page === 'Research runs' && <RunsPage runs={runs} events={events} disabled={working} ready={ready && !demo} perform={perform} refresh={refresh} onStart={() => startRun()} onReview={id => {setSelected(id); navigate('Accounts')}} />}
        {page === 'Outcomes' && <OutcomesPage cohorts={cohorts} accounts={accounts} demo={demo} onReview={id => {setSelected(id); navigate('Accounts')}} />}
        {page === 'Settings' && <SettingsPage bootstrap={bootstrap} disabled={working} perform={perform} refresh={refresh} onClear={async () => {await api('/data', {method: 'DELETE'}); setDemo(false); setSelected(''); setDrawer(null); await refresh()}} />}
      </main>
      <footer className="app-footer"><span>Built around evidence, measured by conversations.</span><span>Customer Intelligence · Local v0.1</span></footer>
    </div>
    {drawer && <EvidenceDrawer data={drawer} modal={mobileDrawer} onClose={closeDrawer} />}
  </div>
}

function SetupStep({done, title, description, onClick}: {done: boolean; title: string; description: string; onClick: () => void}) {
  return <button className="setup-step" onClick={onClick}><span className={'step-check ' + (done ? 'done' : '')}>{done ? <Check size={14} /> : <span />}</span><span><strong>{title}</strong><small>{description}</small></span><ChevronRight size={16} /></button>
}

function ClaimView({claim, onEvidence}: {claim: Claim; onEvidence: (link: Evidence) => void}) {
  return <div className={'claim ' + claim.kind}><div className="claim-heading"><span className={'claim-label ' + claim.kind}>{claim.kind === 'fact' ? <Check size={11} /> : <CircleHelp size={11} />}{statusLabel(claim.kind)}</span><p>{claim.text}</p></div>{claim.reasoning && <p className="claim-reason">{claim.reasoning}</p>}<div className="citation-row">{claim.evidence.map((link, index) => <button key={link.source_id + index} className="citation" aria-label={'View evidence for ' + claim.text} onClick={() => onEvidence(link)}><Link2 size={12} />Evidence {claim.evidence.length > 1 ? index + 1 : ''}<ArrowUpRight size={11} /></button>)}</div></div>
}

function AccountDetail({account, disabled, perform, onEvidence, onRefresh, onOutcome}: {account: Account; disabled: boolean; perform: Perform; onEvidence: (link: Evidence) => void; onRefresh: () => void; onOutcome: (status: OutcomeStatus, note: string) => Promise<void>}) {
  const [tab, setTab] = useState<'brief' | 'chat'>('brief')
  const [status, setStatus] = useState<OutcomeStatus>(account.outcome.status)
  const [note, setNote] = useState(account.outcome.note)
  const brief = account.brief
  return <article className="account-detail"><header className="brief-header"><div><div className="brief-heading-line"><h2>{account.name}</h2><span className={'fit-label ' + brief.fit}><span className="status-dot" />{statusLabel(brief.fit)} fit</span></div><div className="brief-meta">{account.is_demo ? <span>{account.domain} · fictional company</span> : <a href={'https://' + account.domain} target="_blank" rel="noreferrer">{account.domain}<ExternalLink size={12} /></a>}<span>Reviewed {dateLabel(account.updated_at)}</span></div></div><a className="icon-button" href={'/api/accounts/' + account.id + '/export'} title="Download Markdown brief" aria-label="Download Markdown brief"><Download size={18} /></a></header>
    <div className="detail-tabs" role="tablist" aria-label="Account view"><button role="tab" aria-selected={tab === 'brief'} onClick={() => setTab('brief')}><FileText size={15} />Account brief</button><button role="tab" aria-selected={tab === 'chat'} onClick={() => setTab('chat')}><MessageSquare size={15} />Ask about this account</button></div>
    {tab === 'brief' ? <div className="brief-body"><p className="brief-summary">{brief.summary}</p>
      <section className="brief-section"><h3><Target size={18} />Why this account fits</h3>{brief.why_fits.map((claim, index) => <ClaimView key={index} claim={claim} onEvidence={onEvidence} />)}</section>
      <section className="brief-section"><h3><Clock3 size={18} />Why now</h3>{brief.why_now ? <><ClaimView claim={brief.why_now} onEvidence={onEvidence} /><p className="date-note">Event date: {dateLabel(brief.why_now.event_date)}</p></> : <div className="unknown-timing"><Clock3 size={18} /><div><strong>No timing signal found.</strong><p>The account may fit, but the evidence does not establish an active buying window.</p></div></div>}</section>
      <section className="brief-section"><h3><Building2 size={18} />Who matters</h3><p className="section-note">Likely roles to confirm in conversation.</p><div className="people-list">{brief.who_matters.map(person => <div className="person" key={person.role}><span className="person-role">{statusLabel(person.role)}</span><div><strong>{person.name || person.title}</strong><p>{person.basis.text}</p><div className="person-evidence"><span className="uncertainty">{person.confidence} confidence · {person.basis.kind}</span><button className="citation" onClick={() => onEvidence(person.basis.evidence[0])}><Link2 size={12} />Basis</button></div></div></div>)}</div></section>
      <section className="brief-section"><h3><ArrowUpRight size={18} />What could help</h3>{brief.what_could_help.map((action, index) => <div className="helpful-action" key={index}><span className="action-label">{action.kind === 'proposed_asset' ? 'Proposed · to create' : action.kind === 'asset' ? 'From your asset library' : 'Conversation starter'}</span><h4>{action.title}</h4><p>{action.reason}</p>{action.asset_id && <button className="text-button" onClick={() => onEvidence({source_id: action.asset_id!, quote: ''})}>Open asset <ArrowUpRight size={14} /></button>}</div>)}</section>
      <section className="brief-section"><h3><BookOpen size={18} />Evidence</h3><p className="section-note">{account.source_ids.length} saved sources. Open an excerpt to see its origin and dates.</p><div className="source-buttons">{account.source_ids.map((id, index) => <button key={id} className="source-button" onClick={() => onEvidence({source_id: id, quote: ''})}><FileText size={15} />Source {index + 1}<ArrowUpRight size={13} /></button>)}</div></section>
      <section className="outcome-form"><h3>What happened next?</h3><p>Your judgement makes the next shortlist more useful.</p><form onSubmit={event => {event.preventDefault(); perform(() => onOutcome(status, note), 'Outcome saved.')}}><label>Account status<select aria-label="Account status" value={status} onChange={event => setStatus(event.target.value as OutcomeStatus)}>{outcomeOptions.map(value => <option key={value} value={value}>{statusLabel(value)}</option>)}</select></label><label>{status === 'rejected' ? 'Why was this account rejected?' : 'Conversation or review notes'}<textarea rows={3} value={note} onChange={event => setNote(event.target.value)} required={status === 'rejected'} placeholder="What made it relevant—or what did the agent miss?" /></label><div className="form-actions"><Button className="primary" disabled={disabled}>Save outcome</Button><a href={'/api/accounts/' + account.id + '/export?format=csv'} className="text-button">Export CSV <Download size={14} /></a></div></form></section>
      {!account.is_demo && <Button disabled={disabled} onClick={onRefresh}><RefreshCw size={15} />Refresh research in a new run</Button>}
    </div> : <ChatPanel account={account} perform={perform} disabled={disabled} onEvidence={onEvidence} />}
  </article>
}

function ChatPanel({account, perform, disabled, onEvidence}: {account: Account; perform: Perform; disabled: boolean; onEvidence: (evidence: Evidence) => void}) {
  const [messages, setMessages] = useState<Chat[]>([])
  const [question, setQuestion] = useState('')
  useEffect(() => {api<Chat[]>('/accounts/' + account.id + '/chat').then(setMessages).catch(() => {})}, [account.id])
  const submit = (event: FormEvent) => {event.preventDefault(); perform(async () => {const answer = await send<Chat>('/accounts/' + account.id + '/chat', {message: question}); setMessages(current => [...current, answer]); setQuestion('')})}
  return <div className="chat-panel"><div className="chat-intro"><MessageSquare size={25} /><h3>Make sense of the evidence.</h3><p>Ask about fit, missing information or the next useful conversation. Answers use this account’s saved sources.</p><small>{account.is_demo ? 'Demo responses are synthetic and free.' : 'Chat shares the originating run’s model budget.'}</small></div><div className="chat-messages" aria-live="polite">{messages.map(message => <div className="chat-exchange" key={message.id}><p className="chat-question">{message.question}</p><p className="chat-answer">{message.answer}</p><div className="citation-row">{message.evidence.map((evidence, index) => <button className="citation" key={index} onClick={() => onEvidence(evidence)}><Link2 size={13} />Source {index + 1}</button>)}</div></div>)}</div>{messages.length === 0 && <div className="suggested-questions">{['What is the strongest evidence of fit?', 'What should I confirm in a first conversation?'].map(text => <button key={text} onClick={() => setQuestion(text)}>{text}<Plus size={14} /></button>)}</div>}<form className="chat-composer" onSubmit={submit}><label className="sr-only" htmlFor="question">Question about this account</label><textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about this account…" rows={3} required maxLength={3000} /><div><span>Grounded in saved evidence</span><Button className="primary" disabled={disabled || !question.trim()}>{disabled ? <LoaderCircle className="spin" size={15} /> : <Send size={15} />}Ask</Button></div></form></div>
}

function EvidenceDrawer({data, modal, onClose}: {data: {source: Source | null; link: Evidence; error?: string}; modal: boolean; onClose: () => void}) {
  const close = useRef<HTMLButtonElement>(null)
  useEffect(() => {close.current?.focus()}, [])
  const source = data.source
  return <aside className="evidence-drawer" role={modal ? 'dialog' : 'complementary'} aria-modal={modal || undefined} aria-label="Source evidence" onKeyDown={event => {
    if (!modal || event.key !== 'Tab') return
    const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], summary, input, textarea, select, [tabindex="0"]')].filter(element => element.getClientRects().length > 0)
    const first = focusable[0], last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus()}
    else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus()}
  }}><header><div><BookOpen size={18} /><h2>Source evidence</h2></div><button ref={close} className="icon-button" aria-label="Close evidence" onClick={onClose}><X size={20} /></button></header>{source ? <div className="evidence-body"><span className="source-origin">{source.is_demo ? 'Synthetic example' : source.origin === 'upload' ? 'Your imported material' : 'Public source'} · {statusLabel(source.source_type)}</span><h3>{source.title}</h3>{safeLink(source.url) && <a className="source-url" href={safeLink(source.url)} target="_blank" rel="noreferrer">Open original source <ExternalLink size={14} /></a>}<dl className="source-dates"><div><dt>Published / supplied date</dt><dd>{dateLabel(source.published_at)}</dd></div><div><dt>Retrieved / imported</dt><dd>{dateLabel(source.retrieved_at)}</dd></div><div><dt>Account association</dt><dd>{source.account_domain || 'General context; no account assigned'}</dd></div></dl>{data.link.quote && <><h4>Supporting excerpt</h4><blockquote><mark>{data.link.quote}</mark></blockquote></>}<details open={!data.link.quote}><summary>Read extracted source</summary><div className="source-text">{source.text}</div></details><p className="source-disclaimer">An excerpt can support an observation without proving the hypothesis built on it.</p></div> : <div className="evidence-body">{data.error ? <p role="alert">{data.error}</p> : <p><LoaderCircle size={16} className="spin" /> Loading saved source…</p>}</div>}</aside>
}

function PageHeading({title, description, children}: {title: string; description: string; children?: ReactNode}) {
  return <div className="page-heading"><div><h1>{title}<span className="heading-dot">.</span></h1><p>{description}</p></div>{children}</div>
}

function ProfilePage({profile, disabled, onSave}: {profile: Profile | null; disabled: boolean; onSave: (profile: Profile) => void}) {
  const [value, setValue] = useState<Profile>(profile || emptyProfile)
  const [exclusions, setExclusions] = useState(profile?.exclusions.join('\n') || '')
  const fields: {key: keyof Profile; title: string; hint: string}[] = [
    {key: 'offering', title: 'What you can help with', hint: 'Describe your product or service and the outcome it creates.'},
    {key: 'company_type', title: 'Company type', hint: 'For example: B2B software companies with an internal platform team.'},
    {key: 'technology', title: 'Relevant technology', hint: 'Specific platforms, tools or technical workflows that matter.'},
    {key: 'buyer_role', title: 'Buyer role', hint: 'The role most likely to own the problem or sponsor a solution.'},
    {key: 'problem', title: 'Problem or workflow', hint: 'The concrete problem you solve and evidence that would suggest it exists.'},
    {key: 'buying_trigger', title: 'Buying triggers', hint: 'What would make a conversation timely: a migration, expansion or new requirement?'},
  ]
  return <><PageHeading title="A narrow profile. A better shortlist" description="Give the agent a clear definition of an account that deserves your attention." /><div className="form-layout"><form className="editor-form" onSubmit={event => {event.preventDefault(); onSave({...value, exclusions: exclusions.split('\n').map(x => x.trim()).filter(Boolean)})}}>{fields.map(field => <label key={field.key}>{field.title}<span className="field-hint">{field.hint}</span><textarea rows={field.key === 'offering' || field.key === 'problem' ? 3 : 2} value={String(value[field.key])} required minLength={3} onChange={event => setValue({...value, [field.key]: event.target.value})} /></label>)}<label>Clear exclusions<span className="field-hint">One per line. Include company types, situations or constraints that rule an account out.</span><textarea rows={3} value={exclusions} required onChange={event => setExclusions(event.target.value)} placeholder="Consultancies without an internal engineering team" /></label><div className="form-columns"><label>Geography <span className="optional">optional</span><input value={value.geography} onChange={event => setValue({...value, geography: event.target.value})} placeholder="For example: UK and Ireland" /></label><label>Timing signal window <span className="optional">days</span><input type="number" min={1} max={730} value={value.trigger_days} onChange={event => setValue({...value, trigger_days: Number(event.target.value)})} /></label></div><div className="form-actions"><Button className="primary" disabled={disabled}><Check size={16} />Save customer profile</Button><span>Applies to future research runs.</span></div></form><aside className="context-note"><Target size={25} /><h3>Specific is useful.</h3><p>“Uses Terraform and has a platform team” gives the agent something observable to investigate.</p><p>“Needs better infrastructure” is an assumption. The brief should make that distinction visible.</p><hr /><h4>Evidence before volume</h4><p>Exclusions are applied before ranking. A run can return fewer than ten accounts when the evidence is weak.</p></aside></div></>
}

function InputsPage({sources, disabled, perform, refresh, onEvidence}: {sources: Source[]; disabled: boolean; perform: Perform; refresh: () => Promise<void>; onEvidence: (link: Evidence) => void}) {
  const [drafts, setDrafts] = useState<Source[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Source[] | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const blank = (): Source => ({id: '', title: '', text: '', source_type: 'interview', origin: 'upload', url: null, account_domain: null, published_at: null, retrieved_at: new Date().toISOString(), content_hash: '', is_demo: false})
  const update = (index: number, change: Partial<Source>) => setDrafts(current => current.map((draft, at) => at === index ? {...draft, ...change} : draft))
  const importFile = (file?: File) => {if (file) perform(async () => {const form = new FormData(); form.append('file', file); const previews = await api<Source[]>('/imports/preview', {method: 'POST', body: form}); setDrafts(current => [...current, ...previews]); if (fileRef.current) fileRef.current.value = ''})}
  const visible = results || sources
  return <><PageHeading title="Bring your customer context" description="Selected enquiries, interview notes and assets make the research more useful." /><div className="import-toolbar"><div><Upload size={21} /><span><strong>Upload a file or paste your notes</strong><small>TXT, Markdown, PDF, DOCX, EML or CSV · up to 10 MB</small></span></div><input className="sr-only" type="file" ref={fileRef} accept=".txt,.md,.pdf,.docx,.eml,.csv" aria-label="Upload customer input" onChange={event => importFile(event.target.files?.[0])} /><Button disabled={disabled} onClick={() => fileRef.current?.click()}><Upload size={15} />Choose file</Button><Button disabled={disabled} onClick={() => setDrafts(current => [...current, blank()])}><Plus size={15} />Paste notes</Button></div>
    {drafts.length > 0 && <form className="import-preview" onSubmit={event => {event.preventDefault(); perform(async () => {await send('/imports', {sources: drafts}); setDrafts([]); setResults(null); await refresh()}, 'Inputs saved to your local library.')}}><div className="section-heading"><div><h2>Review before saving</h2><p>Edit or redact the extraction. Relevant excerpts may be sent to OpenRouter during research.</p></div><Button type="button" onClick={() => setDrafts([])}>Discard preview</Button></div>{drafts.map((draft, index) => <fieldset className="draft-input" key={index}><legend>Input {index + 1}</legend><div className="form-columns"><label>Title<input value={draft.title} required maxLength={300} onChange={event => update(index, {title: event.target.value})} /></label><label>Type<select value={draft.source_type} onChange={event => update(index, {source_type: event.target.value as SourceType})}>{['inbound', 'interview', 'asset', 'exclusion', 'other'].map(type => <option key={type} value={type}>{statusLabel(type)}</option>)}</select></label></div><div className="form-columns"><label>Company domain <span className="optional">optional</span><input value={draft.account_domain || ''} placeholder="company.com" onChange={event => update(index, {account_domain: event.target.value || null})} /><span className="field-hint">Confirm the association. Leave blank for general context.</span></label><label>Source date <span className="optional">if known</span><input type="date" value={draft.published_at?.slice(0, 10) || ''} onChange={event => update(index, {published_at: event.target.value || null})} /></label></div><label>Extracted content<textarea rows={7} required maxLength={150000} value={draft.text} onChange={event => update(index, {text: event.target.value})} /></label></fieldset>)}<Button className="primary" disabled={disabled}><Check size={16} />Save {drafts.length === 1 ? 'input' : `${drafts.length} inputs`}</Button></form>}
    <section className="library"><div className="section-heading"><div><h2>Your source library</h2><p>Uploaded context and evidence collected during live research.</p></div><form className="search-input" onSubmit={event => {event.preventDefault(); perform(async () => setResults(await api<Source[]>('/sources?query=' + encodeURIComponent(query))))}}><Search size={16} /><input aria-label="Search source library" value={query} onChange={event => {setQuery(event.target.value); if (!event.target.value) setResults(null)}} placeholder="Search your sources…" /><button aria-label="Run source search"><ArrowRight size={15} /></button></form></div>{visible.length === 0 ? <div className="empty-state"><FolderOpen size={30} /><h3>{query ? 'No matching sources' : 'Your context starts here'}</h3><p>{query ? 'Try another phrase from your notes.' : 'Add an enquiry, interview note or useful example. You can start public research without uploads.'}</p></div> : <div className="source-library">{visible.map(source => <div className="library-row" key={source.id}><FileText size={19} /><button className="library-title" onClick={() => onEvidence({source_id: source.id, quote: ''})}><strong>{source.title}</strong><span>{source.account_domain || 'General context'} · {dateLabel(source.retrieved_at)}</span></button><span className="subtle-pill">{statusLabel(source.source_type)}</span><button className="icon-button" title="Delete source" aria-label={'Delete ' + source.title} disabled={disabled} onClick={() => perform(async () => {await api('/sources/' + source.id, {method: 'DELETE'}); setResults(null); await refresh()}, 'Source deleted.')}><Trash2 size={15} /></button></div>)}</div>}</section></>
}

function RunsPage({runs, events, disabled, ready, perform, refresh, onStart, onReview}: {runs: Run[]; events: RunEvent[]; disabled: boolean; ready: boolean; perform: Perform; refresh: () => Promise<void>; onStart: () => void; onReview: (id: string) => void}) {
  return <><PageHeading title="Research with a clear stopping point" description="Follow the work, see the spending and pick up where you left off."><Button className="primary" disabled={disabled || !ready || runs.some(run => run.status === 'running')} onClick={onStart}><Plus size={16} />Find accounts</Button></PageHeading>{runs.length === 0 ? <div className="empty-state large"><Play size={32} /><h2>No research runs yet</h2><p>Complete your profile and API settings, then start your first shortlist.</p></div> : <div className="runs-list">{runs.map(run => <RunRow key={run.id} run={run} disabled={disabled} perform={perform} refresh={refresh} onReview={onReview} events={events.filter(event => event.run_id === run.id)} />)}</div>}</>
}

function RunRow({run, disabled, perform, refresh, onReview, events}: {run: Run; disabled: boolean; perform: Perform; refresh: () => Promise<void>; onReview: (id: string) => void; events: RunEvent[]}) {
  const [budget, setBudget] = useState(run.settings.model_budget)
  const [credits, setCredits] = useState(run.settings.max_search_queries)
  const [pageLimit, setPageLimit] = useState(run.settings.max_pages_fetched)
  const [callLimit, setCallLimit] = useState(run.settings.max_llm_iterations)
  const [savedEvents, setSavedEvents] = useState<RunEvent[]>([])
  const allEvents = events.length ? events : savedEvents
  const loadEvents = () => {
    const stream = new EventSource('/api/runs/' + run.id + '/events')
    stream.addEventListener('progress', ((event: MessageEvent) => {setSavedEvents(JSON.parse(event.data).events); stream.close()}) as EventListener)
    stream.onerror = () => stream.close()
  }
  return <article className="run-row"><div className="run-row-heading"><div><h2>{run.is_demo ? 'Example research run' : 'Account research'}<span className={'run-status ' + run.status}>{run.status === 'running' && <LoaderCircle className="spin" size={12} />}{statusLabel(run.status)}</span></h2><p>{dateLabel(run.created_at)} · {run.profile.company_type}</p></div><div className="run-actions">{run.status === 'running' && <Button disabled={disabled} onClick={() => perform(async () => {await send('/runs/' + run.id + '/cancel'); await refresh()})}><Square size={13} />Stop</Button>}{['paused', 'interrupted', 'cancelled'].includes(run.status) && <Button className="primary" disabled={disabled} onClick={() => perform(async () => {await send('/runs/' + run.id + '/resume'); await refresh()})}><Play size={14} />Resume</Button>}{run.account_ids.length > 0 && <Button onClick={() => onReview(run.account_ids[0])}>Review accounts <ArrowRight size={15} /></Button>}</div></div><p className="run-stage">{run.stage}</p><div className="run-measures"><span><strong>{run.account_ids.length}</strong> recommendations</span><span>{run.processed} of {run.candidate_count} candidates reviewed</span><span>{money(run.costs.model_usd)} / {money(run.settings.model_budget)} model budget{run.costs.has_estimates ? ' · includes estimates' : ''}</span><span>{run.costs.search_queries} / {run.settings.max_search_queries} searches · {run.costs.pages_fetched} / {run.settings.max_pages_fetched} pages</span></div>{run.status === 'running' && <progress max={Math.max(run.candidate_count, 1)} value={run.processed} aria-label="Candidates reviewed" />}{run.error && <p className="inline-error">{run.error}</p>}{run.degraded && <p className="inline-error">Research is incomplete: some sources or services were unavailable. See the activity log for details.</p>}<ModelUsage run={run} /><div className="run-details-row"><details onToggle={event => {if (event.currentTarget.open && !allEvents.length) loadEvents()}}><summary>Activity and input review</summary>{run.input_review.observations.map((observation, index) => <p key={'observation' + index}><strong>Observation:</strong> {observation}</p>)}{run.input_review.hypotheses.map((hypothesis, index) => <p key={'hypothesis' + index}><strong>Hypothesis:</strong> {hypothesis}</p>)}<ol className="event-list">{allEvents.map(event => <li key={event.id}><time>{new Date(event.at).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'})}</time><span>{event.message}</span></li>)}</ol>{allEvents.length === 0 && <p className="muted">No additional activity recorded.</p>}</details>{!run.is_demo && run.status !== 'running' && <details><summary>Adjust this run’s budget</summary><form onSubmit={event => {event.preventDefault(); perform(async () => {await send('/runs/' + run.id + '/budget', {model_budget: budget, max_search_queries: credits, max_pages_fetched: pageLimit, max_llm_iterations: callLimit}, 'PUT'); await refresh()}, 'Run budget updated. Resume when ready.')}}><div className="form-columns"><label>Model cap (USD)<input type="number" min={0.1} max={100} step={0.1} value={budget} onChange={event => setBudget(Number(event.target.value))} /></label><label>Search query limit<input type="number" min={1} max={100} value={credits} onChange={event => setCredits(Number(event.target.value))} /></label><label>Page limit<input type="number" min={1} max={120} value={pageLimit} onChange={event => setPageLimit(Number(event.target.value))} /></label><label>Model calls per account<input type="number" min={5} max={12} value={callLimit} onChange={event => setCallLimit(Number(event.target.value))} /></label></div><Button disabled={disabled}>Save run budget</Button></form></details>}</div></article>
}

function OutcomesPage({cohorts, accounts, demo, onReview}: {cohorts: Cohort[]; accounts: Account[]; demo: boolean; onReview: (id: string) => void}) {
  return <><PageHeading title="Measure the conversations" description="A recommendation earns its value when it leads to a relevant conversation." /><div className="outcomes-intro"><MessageSquare size={26} /><div><h2>From a promising account to a useful conversation.</h2><p>Record what happened in each account brief. Conversion is relevant conversations divided by unique recommended accounts, grouped by the week they were first recommended. Demo examples are excluded.</p></div></div>{cohorts.length ? <div className="table-wrap"><table><caption>Live recommendation cohorts</caption><thead><tr><th>Week beginning</th><th>Recommended</th><th>Contacted</th><th>Relevant conversations</th><th>Uncontacted</th><th>Rejected</th><th>Conversion</th></tr></thead><tbody>{cohorts.map(cohort => <tr key={cohort.week}><td>{dateLabel(cohort.week)}</td><td>{cohort.recommended}</td><td>{cohort.contacted}</td><td>{cohort.relevant}</td><td>{cohort.uncontacted}</td><td>{cohort.rejected}</td><td>{Math.round(cohort.conversion * 100)}%</td></tr>)}</tbody></table></div> : <div className="empty-state"><MessageSquare size={28} /><h3>Your conversation history will grow here</h3><p>Run live research and record account outcomes to see your first cohort.</p></div>}<section className="library"><h2>{demo ? 'Practice recording an outcome' : 'Accounts to follow up'}</h2><div className="source-library">{accounts.map(account => <button className="outcome-row" key={account.id} onClick={() => onReview(account.id)}><span><strong>{account.name}</strong><small>{account.outcome.note || 'Add your judgement in the account brief.'}</small></span><span className="subtle-pill">{statusLabel(account.outcome.status)}</span><ArrowUpRight size={16} /></button>)}</div></section></>
}

function SettingsPage({bootstrap, disabled, perform, refresh, onClear}: {bootstrap: Bootstrap; disabled: boolean; perform: Perform; refresh: () => Promise<void>; onClear: () => Promise<void>}) {
  const [settings, setSettings] = useState<Settings>(bootstrap.settings)
  const [modelsValid, setModelsValid] = useState(false)
  const [allowed, setAllowed] = useState(settings.allowed_domains.join('\n'))
  const [blocked, setBlocked] = useState(settings.blocked_domains.join('\n'))
  const [checks, setChecks] = useState<Record<string, string> | null>(null)
  const [deletion, setDeletion] = useState('')
  return <><PageHeading title="Your tools. Your boundaries" description="Connect research services and keep control of sources, spending and stored data." /><div className="settings-layout"><section className="settings-section"><div className="section-heading"><div><h2>Research connections</h2><p>Keys stay on the backend in {bootstrap.credential_storage}.</p></div><Button disabled={disabled} onClick={() => perform(async () => setChecks(await send('/check-connections')))}><RefreshCw size={14} />Check connections</Button></div>{(['openrouter'] as const).map(name => <CredentialRow key={name} name={name} storage={bootstrap.credential_storage} state={bootstrap.credentials[name]} check={checks?.[name]} disabled={disabled} onSave={value => perform(async () => {await send('/credentials/' + name, {value}, 'PUT'); setChecks(current => current ? {...current, [name]: ''} : null); await refresh()}, value ? 'Key saved.' : 'Keychain entry removed.')} />)}<div className="self-hosted-research"><h3>Self-hosted research</h3><p>SearXNG discovers pages. Crawl4AI retrieves and extracts evidence through your authenticated research gateway.</p><p>{checks?.research || "Start the Docker stack, then use Check connections to verify the research services."}</p><code>make up · make connect-native</code></div><p className="privacy-note"><ShieldCheck size={16} />Selected excerpts are sent to OpenRouter with ZDR routing. Self-hosted SearXNG handles discovery; Crawl4AI reads permitted public sources. Paid search is disabled.</p></section>
      <form className="settings-section" onSubmit={event => {event.preventDefault(); if (!modelsValid) return; perform(async () => {await send('/settings', {...settings, allowed_domains: allowed.split('\n').map(x => x.trim()).filter(Boolean), blocked_domains: blocked.split('\n').map(x => x.trim()).filter(Boolean)}, 'PUT'); await refresh()}, 'Settings saved for future runs.')}}><div className="section-heading"><div><h2>Models by task</h2><p>Changes apply to future runs. Existing runs and their account chat keep their original models.</p></div><SlidersHorizontal size={21} /></div><ModelSettings value={settings.models} defaults={bootstrap.model_defaults} disabled={disabled} onChange={models => setSettings(current => ({...current, models}))} onValidity={setModelsValid} /><h3>Research limits</h3><div className="form-columns three"><label>Model cap per run (USD)<input type="number" min={0.1} max={100} step={0.1} value={settings.model_budget} onChange={event => setSettings({...settings, model_budget: Number(event.target.value)})} /></label><label>Search queries per run<input type="number" min={1} max={100} value={settings.max_search_queries} onChange={event => setSettings({...settings, max_search_queries: Number(event.target.value)})} /></label><label>Maximum candidates<input type="number" min={1} max={40} value={settings.candidate_limit} onChange={event => setSettings({...settings, candidate_limit: Number(event.target.value)})} /></label></div><div className="form-columns three"><label>Pages per run<input type="number" min={1} max={120} value={settings.max_pages_fetched} onChange={event => setSettings({...settings, max_pages_fetched: Number(event.target.value)})} /></label><label>Search rounds per account<input type="number" min={1} max={3} value={settings.max_search_iterations} onChange={event => setSettings({...settings, max_search_iterations: Number(event.target.value)})} /></label><label>Model calls per account<input type="number" min={5} max={12} value={settings.max_llm_iterations} onChange={event => setSettings({...settings, max_llm_iterations: Number(event.target.value)})} /></label></div><h3>Permitted public sources</h3><p className="field-hint">Company websites, product documentation, public job adverts and relevant technical discussions. Domain rules also apply to JavaScript resources.</p><div className="form-columns"><label>Allow only these domains<span className="field-hint">One per line. Leave blank to allow public websites.</span><textarea rows={4} value={allowed} onChange={event => setAllowed(event.target.value)} /></label><label>Blocked domains<span className="field-hint">One per line. Includes each domain’s subdomains.</span><textarea rows={4} value={blocked} onChange={event => setBlocked(event.target.value)} /></label></div><label className="checkbox-label"><input type="checkbox" checked={settings.browser_fallback} onChange={event => setSettings({...settings, browser_fallback: event.target.checked})} /><span>Use isolated Chromium when a permitted page requires JavaScript</span></label><Button className="primary" disabled={disabled || !modelsValid}><Check size={15} />Save research settings</Button></form>
      <section className="settings-section"><h2>Your local data</h2><p>Stored on this Mac in:</p><code className="data-path">{bootstrap.data_directory}</code><div className="form-actions"><a className="button" href="/api/export"><Download size={15} />Export application data</a><a className="text-button" href="/docs" target="_blank" rel="noreferrer">Local API reference <ArrowUpRight size={15} /></a></div><details className="delete-data"><summary>Delete research data</summary><p>This removes imported material, research, briefs, chats, outcomes and checkpoints. Your profile, settings and credentials remain. The separate research gateway retains its public-page cache, evidence and audit records in Docker; see the operations guide for complete Docker data removal.</p><form onSubmit={event => {event.preventDefault(); if (deletion === 'DELETE') perform(async () => {await onClear(); setDeletion('')}, 'Research data deleted.')}}><label>Type DELETE to confirm<input value={deletion} onChange={event => setDeletion(event.target.value)} autoComplete="off" /></label><Button className="danger" disabled={disabled || deletion !== 'DELETE'}><Trash2 size={15} />Delete research data</Button></form></details></section>
      <section className="settings-section"><h2>About and credits</h2><p>Customer Intelligence Agent combines LangGraph, OpenRouter, SearXNG and Crawl4AI for evidence-led account research.</p><p>This product includes software developed by UncleCode (<a href="https://x.com/unclecode" target="_blank" rel="noreferrer">https://x.com/unclecode</a>) as part of the Crawl4AI project (<a href="https://github.com/unclecode/crawl4ai" target="_blank" rel="noreferrer">https://github.com/unclecode/crawl4ai</a>).</p><a className="text-button" href="/third-party-notices.txt" target="_blank" rel="noreferrer">Third-party notices <ArrowUpRight size={15} /></a></section></div></>
}

function CredentialRow({name, storage, state, check, disabled, onSave}: {name: string; storage: string; state: {configured: boolean; environment: boolean}; check?: string; disabled: boolean; onSave: (value: string) => Promise<boolean>}) {
  const [value, setValue] = useState('')
  return <form className="credential-row" onSubmit={async event => {event.preventDefault(); if (await onSave(value)) setValue('')}}><div><h3>{'OpenRouter'}</h3><p>{name === 'openrouter' ? 'Source analysis, briefs and questions' : 'Public web discovery'}</p><span className={'connection-status ' + (state.configured ? 'connected' : '')}><span className="status-dot" />{check || (state.environment ? 'Configured through environment' : state.configured ? (storage === 'macOS Keychain' ? 'Key saved in Keychain' : 'Key saved in private volume') : 'Key needed')}</span></div><div className="credential-fields"><label><span className="sr-only">{name} API key</span><input type="password" autoComplete="new-password" placeholder={state.configured ? 'Replace API key…' : 'Paste API key…'} value={value} onChange={event => setValue(event.target.value)} /></label><Button disabled={disabled || !value.trim()}>Save key</Button>{state.configured && !state.environment && <button type="button" className="icon-button" title="Remove Keychain entry" aria-label={'Remove ' + name + ' key'} disabled={disabled} onClick={() => onSave('')}><Trash2 size={15} /></button>}</div></form>
}
