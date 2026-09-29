import { useEffect, useState } from 'react'
import './App.css'
import { checkApiHealth, recallDefects, reflectOnRegression, retainDefect } from './api'

const navItems = ['Overview', 'Test Cases', 'Defect History', 'Regression Analysis']

const failures = [
  { name: 'Checkout retry loop', severity: 'Critical', suite: 'payments', count: '12 failed', trend: '+7 vs last run' },
  { name: 'Session token expiry', severity: 'High', suite: 'auth', count: '8 failed', trend: '+2 since release' },
  { name: 'CSV export mismatch', severity: 'Medium', suite: 'reports', count: '4 failed', trend: 'Recurring pattern' },
]

const insights = [
  { title: 'Retry logic regression', status: 'High risk', score: '92%', detail: 'Matches 3 historical defects in payments and auth flow.', evidence: 'Same timeout signatures; 4 of 6 failed cases share identical stack traces.' },
  { title: 'Permission boundary check', status: 'Medium risk', score: '76%', detail: 'Previous incident caused stale session grant bypass.', evidence: 'Identical user role states found in 2 prior releases.' },
  { title: 'Report generation drift', status: 'Low risk', score: '59%', detail: 'Lower confidence, but high recurrence in saved exports.', evidence: 'CSV schema mismatch observed after locale changes.' },
]

const testRecommendations = [
  { name: 'P-214: Payment retry fallback', priority: 'Run now', result: 'Recommended', tag: 'Retry logic' },
  { name: 'A-89: Session renewal path', priority: 'Queued', result: 'Needs evidence', tag: 'Auth' },
  { name: 'R-33: Export snapshot parity', priority: 'Run tonight', result: 'Suggested', tag: 'Reports' },
]

const historicDefects = [
  { id: 'BUG-4821', title: 'Payment retry loop after gateway timeout', status: 'Confirmed', evidence: '2 previous incidents, same gateway timeout and refresh cycle.' },
  { id: 'BUG-3764', title: 'Session renewal mismatch on re-auth', status: 'Likely recur', evidence: 'Role state drift + stale token persisted across 2 regressions.' },
  { id: 'BUG-2910', title: 'CSV output missing rows after locale update', status: 'Observed', evidence: 'Schema drift matched export snapshot diff from prior release.' },
]

function DemoNotice() {
  return <div className="demo-notice"><strong>DEMO DATA</strong><span>Sample metrics and records below are not live Hindsight results.</span></div>
}

function Overview() {
  return <>
    <DemoNotice />
    <section className="stats-grid" aria-label="Demo summary metrics">
      <article className="metric-card accent"><div className="metric-label">Currently failing</div><div className="metric-value">24</div><div className="metric-meta">Across 6 suites</div></article>
      <article className="metric-card"><div className="metric-label">Historical recurrence</div><div className="metric-value">18</div><div className="metric-meta">Defects likely to reappear</div></article>
      <article className="metric-card"><div className="metric-label">Recommended tests</div><div className="metric-value">9</div><div className="metric-meta">High-priority regression checks</div></article>
    </section>
    <section className="content-grid">
      <div className="panel-column">
        <section className="panel">
          <div className="panel-header"><div><div className="tiny-label">What is failing now</div><h2>Current failures</h2></div><span className="demo-tag">DEMO DATA</span></div>
          <div className="stack-list">{failures.map((item) => <div key={item.name} className="stack-row"><div className="stack-main"><div className={`status-badge ${item.severity.toLowerCase()}`}>{item.severity}</div><div><div className="row-title">{item.name}</div><div className="row-meta">{item.suite}</div></div></div><div className="row-right"><div className="row-count">{item.count}</div><div className="row-trend">{item.trend}</div></div></div>)}</div>
        </section>
        <section className="panel">
          <div className="panel-header"><div><div className="tiny-label">Regression selection</div><h2>Recommended tests</h2></div><span className="demo-tag">DEMO DATA</span></div>
          <TestCaseRows />
        </section>
      </div>
      <div className="panel-column">
        <section className="panel">
          <div className="panel-header"><div><div className="tiny-label">Prior evidence</div><h2>Likely recurrence risk</h2></div><span className="demo-tag">DEMO DATA</span></div>
          <div className="risk-list">{insights.map((item) => <article key={item.title} className="risk-card"><div className="risk-topline"><div className="risk-title">{item.title}</div><span className={`risk-status ${item.status.toLowerCase().replace(/\s+/g, '-')}`}>{item.status}</span></div><div className="risk-score">{item.score}</div><p>{item.detail}</p><div className="risk-proof"><span>Sample evidence · DEMO DATA</span><strong>{item.evidence}</strong></div></article>)}</div>
        </section>
      </div>
    </section>
    <section className="panel lower-panel">
      <div className="panel-header"><div><div className="tiny-label">Defect memory</div><h2>Historical defects most likely to recur</h2></div><span className="demo-tag">DEMO DATA</span></div>
      <div className="historic-grid">{historicDefects.map((item) => <article key={item.id} className="history-card"><div className="history-meta">{item.id}</div><div className="history-title">{item.title}</div><div className="history-status">{item.status}</div><p>{item.evidence}</p></article>)}</div>
    </section>
  </>
}

function TestCaseRows() {
  return <div className="table-list">{testRecommendations.map((item) => <div key={item.name} className="table-row"><div><div className="row-title">{item.name}</div><div className="row-meta">{item.tag}</div></div><div className="table-meta">{item.result}</div><span className="chip-button">{item.priority}</span></div>)}</div>
}

function TestCases() {
  return <><DemoNotice /><section className="panel"><div className="panel-header"><div><div className="tiny-label">Regression selection</div><h2>Recommended test cases</h2></div><span className="demo-tag">DEMO DATA</span></div><TestCaseRows /></section></>
}

function formatMetadata(metadata) {
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return []
  return Object.entries(metadata).filter(([, value]) => value !== null && value !== undefined && value !== '')
}

function RegressionAnalysis() {
  const [component, setComponent] = useState('')
  const [requirementId, setRequirementId] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')

  async function analyze(event) {
    event.preventDefault()
    if (state === 'loading') return
    const payload = { budget: 'mid' }
    if (component.trim()) payload.component = component.trim()
    if (requirementId.trim()) payload.requirement_id = requirementId.trim()
    if (!payload.component && !payload.requirement_id) {
      setError('Enter a requirement ID or component name to analyze.')
      setState('error')
      setAnalysis(null)
      return
    }

    setState('loading')
    setError('')
    setAnalysis(null)
    try {
      const recall = await recallDefects(payload)
      const reflection = await reflectOnRegression(payload)
      setAnalysis({ recall, reflection })
      setState('success')
    } catch (requestError) {
      setError(requestError.message || 'The analysis request failed.')
      setState('error')
    }
  }

  const memories = analysis?.recall?.memories ?? []

  return <div className="workflow-stack">
    <section className="panel workflow-panel">
      <div className="panel-header"><div><div className="tiny-label">Hindsight Cloud</div><h2>Analyze a requirement or component</h2></div><span className="live-tag"><span /> LIVE API</span></div>
      <p className="workflow-intro">Search retained QA history and generate regression guidance from returned evidence.</p>
      <form className="workflow-form analysis-form" onSubmit={analyze}>
        <label>Requirement ID <span>Optional</span><input value={requirementId} onChange={(event) => setRequirementId(event.target.value)} placeholder="e.g. REQ-CHK-999" /></label>
        <div className="form-divider" aria-hidden="true">or</div>
        <label>Component name <span>Optional</span><input value={component} onChange={(event) => setComponent(event.target.value)} placeholder="e.g. checkout" /></label>
        <button className="primary-button" type="submit" disabled={state === 'loading'}>{state === 'loading' ? 'Analyzing…' : 'Analyze Regression Risk'}</button>
      </form>
      {state === 'loading' && <p className="inline-state" role="status">Searching Hindsight memories and generating analysis…</p>}
      {state === 'error' && <div className="feedback error-feedback" role="alert">{error}</div>}
    </section>
    {state === 'success' && analysis && <>
      {memories.length === 0 && <div className="feedback empty-feedback" role="status">No historical memories were returned for this query. No historical evidence or risk score is inferred.</div>}
      <section className="panel result-panel">
        <div className="panel-header"><div><div className="tiny-label">Generated by Hindsight reflect</div><h2>Regression risk analysis</h2></div><span className="live-tag"><span /> API RESPONSE</span></div>
        {analysis.reflection.answer ? <p className="analysis-answer">{analysis.reflection.answer}</p> : <p className="empty-copy">The API returned no generated analysis.</p>}
      </section>
      <section className="panel result-panel">
        <div className="panel-header"><div><div className="tiny-label">Returned by Hindsight recall</div><h2>Historical evidence <span className="result-count">{analysis.recall.memory_count ?? memories.length}</span></h2></div><span className="live-tag"><span /> API RESPONSE</span></div>
        {memories.length === 0 ? <p className="empty-copy">No historical memories to display.</p> : <div className="evidence-list">{memories.map((memory, index) => {
          const metadata = formatMetadata(memory.metadata)
          const defectId = memory.metadata?.defect_id || memory.document_id
          return <article className="evidence-item" key={memory.id || `${memory.text}-${index}`}>
            <div className="evidence-heading"><div>{defectId && <span className="defect-reference">{defectId}</span>}{memory.type && <span className="memory-type">{memory.type}</span>}</div>{memory.mentioned_at && <time>{new Date(memory.mentioned_at).toLocaleDateString()}</time>}</div>
            <p>{memory.text || 'Memory returned without text.'}</p>
            {metadata.length > 0 && <dl className="metadata-list">{metadata.map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}
          </article>
        })}</div>}
      </section>
    </>}
  </div>
}

const emptyDefect = { defect_id: '', title: '', affected_component: '', requirement_id: '', severity: '', root_cause: '', fix: '', related_test_cases: '' }

function DefectHistory() {
  const [form, setForm] = useState(emptyDefect)
  const [state, setState] = useState('idle')
  const [feedback, setFeedback] = useState('')

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  async function submitDefect(event) {
    event.preventDefault()
    if (state === 'loading') return
    setState('loading')
    setFeedback('')
    const payload = {
      defect_id: form.defect_id.trim(),
      title: form.title.trim(),
      affected_component: form.affected_component.trim(),
      requirement_id: form.requirement_id.trim(),
      severity: form.severity.trim(),
      root_cause: form.root_cause.trim(),
      fix: form.fix.trim(),
      related_test_cases: form.related_test_cases.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
    }
    try {
      const result = await retainDefect(payload)
      setFeedback(result.message || `Defect ${result.defect_id || payload.defect_id} stored successfully.`)
      setState('success')
    } catch (requestError) {
      setFeedback(requestError.message || 'The defect could not be stored.')
      setState('error')
    }
  }

  return <section className="panel workflow-panel">
    <div className="panel-header"><div><div className="tiny-label">Hindsight Cloud</div><h2>Store a defect memory</h2></div><span className="live-tag"><span /> USER SUBMISSION</span></div>
    <p className="workflow-intro">Only defects submitted here are sent to the real memory bank. Nothing is added automatically.</p>
    <form className="workflow-form defect-form" onSubmit={submitDefect}>
      <label>Defect ID<input name="defect_id" value={form.defect_id} onChange={updateField} required minLength="1" placeholder="e.g. BUG-4821" /></label>
      <label>Title<input name="title" value={form.title} onChange={updateField} required minLength="1" placeholder="Short defect summary" /></label>
      <label>Affected component<input name="affected_component" value={form.affected_component} onChange={updateField} required minLength="1" placeholder="e.g. checkout" /></label>
      <label>Requirement ID<input name="requirement_id" value={form.requirement_id} onChange={updateField} required minLength="1" placeholder="e.g. REQ-CHK-999" /></label>
      <label>Severity<input name="severity" value={form.severity} onChange={updateField} required minLength="1" placeholder="e.g. critical" /></label>
      <label className="form-wide">Root cause<textarea name="root_cause" value={form.root_cause} onChange={updateField} required minLength="1" rows="3" placeholder="What caused the defect?" /></label>
      <label className="form-wide">Fix<textarea name="fix" value={form.fix} onChange={updateField} required minLength="1" rows="3" placeholder="How was it resolved?" /></label>
      <label className="form-wide">Related test cases <span>Comma or newline separated</span><textarea name="related_test_cases" value={form.related_test_cases} onChange={updateField} rows="2" placeholder="TC-CHK-001, TC-CHK-002" /></label>
      <div className="form-actions"><button className="primary-button" type="submit" disabled={state === 'loading'}>{state === 'loading' ? 'Saving…' : 'Store Defect Memory'}</button></div>
    </form>
    {state === 'loading' && <p className="inline-state" role="status">Sending defect to Hindsight…</p>}
    {state === 'success' && <div className="feedback success-feedback" role="status">{feedback}</div>}
    {state === 'error' && <div className="feedback error-feedback" role="alert">{feedback}</div>}
  </section>
}

function App() {
  const [activePage, setActivePage] = useState('Overview')
  const [apiHealthy, setApiHealthy] = useState(null)

  useEffect(() => {
    let active = true
    checkApiHealth().then(() => { if (active) setApiHealthy(true) }).catch(() => { if (active) setApiHealthy(false) })
    return () => { active = false }
  }, [])

  const pageTitles = {
    Overview: ['Overview', 'Regression monitor'],
    'Test Cases': ['Test Cases', 'Recommended test cases'],
    'Defect History': ['Defect History', 'Defect memory'],
    'Regression Analysis': ['Regression Analysis', 'Analyze regression risk'],
  }

  return <div className="dashboard-shell">
    <aside className="sidebar">
      <div className="brand-block"><div className="brand-mark">R</div><div><div className="brand-name">Regression Intelligence</div><div className="brand-subtitle">Memory-driven QA</div></div></div>
      <nav className="sidebar-nav" aria-label="Sidebar navigation">{navItems.map((item) => <button key={item} type="button" className={activePage === item ? 'nav-item active' : 'nav-item'} aria-current={activePage === item ? 'page' : undefined} onClick={() => setActivePage(item)}><span className="nav-dot" aria-hidden="true" />{item}</button>)}</nav>
      <div className="sidebar-card api-health-card"><div className="tiny-label">Backend API</div><div className={`health-state ${apiHealthy === true ? 'connected' : apiHealthy === false ? 'disconnected' : ''}`}><span />{apiHealthy === true ? 'Connected' : apiHealthy === false ? 'Unavailable' : 'Checking…'}</div><div className="mini-meta">Hindsight Cloud via FastAPI</div></div>
      <div className="sidebar-card coverage-card"><div className="tiny-label">Coverage signal · DEMO DATA</div><div className="mini-stat">87%</div><div className="mini-meta">Sample regression confidence</div></div>
    </aside>
    <main className="main-panel">
      <header className="topbar"><div><div className="eyebrow">{pageTitles[activePage][0]}</div><h1>{pageTitles[activePage][1]}</h1></div><div className="topbar-tools"><div className="project-pill"><span className="pill-label">Project</span><span>Checkout 2.4</span></div><span className="api-indicator"><span className={apiHealthy === false ? 'offline' : ''} />{apiHealthy === true ? 'API connected' : apiHealthy === false ? 'API offline' : 'Connecting'}</span></div></header>
      <div className="page-content">
        {activePage === 'Overview' && <Overview />}
        {activePage === 'Test Cases' && <TestCases />}
        {activePage === 'Defect History' && <DefectHistory />}
        {activePage === 'Regression Analysis' && <RegressionAnalysis />}
      </div>
    </main>
  </div>
}

export default App
