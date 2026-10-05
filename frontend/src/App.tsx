import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  FileCode2,
  FileJson,
  Files,
  FolderGit2,
  GitBranch,
  HelpCircle,
  Layers,
  ListChecks,
  LoaderCircle,
  Play,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Upload,
  Waypoints,
  X,
  AlertTriangle,
} from 'lucide-react'
import {
  api,
  collectEvidence,
  explainFailure,
  explainEvidenceCheck,
  indexSchema,
  isRecord,
  parseReport,
  toolError,
  toolOutput,
} from './data'
import type { Evidence, IndexSummary, Report, Workspace } from './data'

const sampleIssue =
  'MCP_SERVER_NAME is an empty string but server startup accepts it. Locate the validation path and propose a regression test.'
const tabs = [
  { id: 'overview', label: '调查摘要', icon: BookOpen },
  { id: 'code', label: '代码证据', icon: Code2 },
  { id: 'trace', label: '调用轨迹', icon: Waypoints },
  { id: 'tests', label: '验证计划', icon: ListChecks },
] as const
type Tab = (typeof tabs)[number]['id']
const methodNames: Record<string, string> = {
  bm25: 'BM25 · 关键词相关性',
  keyword: 'Keyword · 基础关键词',
  vector: 'Vector · 语义检索',
  hybrid: 'Hybrid · 混合检索',
  rerank: 'Rerank · 候选重排',
}
const toolNames: Record<string, string> = {
  read_file: '读取源码',
  search_code: '搜索代码',
  find_symbol: '查找定义与赋值',
  find_callers: '查找候选调用方',
}

function CodeBlock({ evidence }: { evidence: Evidence }) {
  return (
    <div className="code-block">
      <div className="code-top">
        <span>
          <FileCode2 size={14} />
          {evidence.path}
        </span>
        <span>
          L{evidence.start}–{evidence.end}
        </span>
      </div>
      <pre>
        {evidence.content
          .replace(/\n$/, '')
          .split('\n')
          .map((line, i) => (
            <div className="code-line" key={i}>
              <span className="line-no">{evidence.start + i}</span>
              <code>{line || ' '}</code>
            </div>
          ))}
      </pre>
      {evidence.truncated && <div className="code-notice">此片段已截断，尚未展示完整实现。</div>}
    </div>
  )
}

function ToolDetails({ output }: { output: string }) {
  const value = toolOutput(output)
  const error = toolError(output)
  if (error)
    return (
      <div className="tool-error">
        <AlertTriangle size={16} />
        <div>
          <strong>本次工具调用失败</strong>
          <p>{error}</p>
          <small>这是一条真实错误；后续步骤可能重试，不代表整个调查失败。</small>
        </div>
      </div>
    )
  if (Array.isArray(value))
    return (
      <div className="tool-matches">
        {value.length === 0 && <p>没有找到匹配的代码。</p>}
        {value.map((item, i) =>
          isRecord(item) ? (
            <details key={i}>
              <summary>
                <FileCode2 size={14} />
                {String(item.file_path ?? '')}
                <span>{String(item.symbol ?? item.caller ?? '')}</span>
              </summary>
              {item.match_kind === 'name_candidate' && (
                <p className="caller-note">
                  按名称匹配的候选调用位置；尚未解析类型、别名或动态分派，需阅读源码确认。
                </p>
              )}
              {(item.kind === 'assignment' || item.kind === 'import') && (
                <p className="caller-note">
                  {item.kind === 'assignment' ? '赋值或声明候选' : '导入位置'}；需继续阅读源码，确认实际运行时使用的值。
                </p>
              )}
              <pre>{String(item.content ?? '')}</pre>
            </details>
          ) : null,
        )}
      </div>
    )
  if (isRecord(value) && typeof value.content === 'string')
    return (
      <>
        <p className="muted small">
          {String(value.file_path ?? '')} · {String(value.start_line ?? '')}–
          {String(value.end_line ?? '')} 行{value.content_truncated === true ? ' · 内容有截断' : ''}
        </p>
        <pre className="tool-code">{value.content}</pre>
      </>
    )
  return (
    <pre className="tool-code">
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  )
}

export default function App() {
  const [report, setReport] = useState<Report | null>(null)
  const [source, setSource] = useState<'demo' | 'import' | 'live'>('demo')
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [connected, setConnected] = useState(false)
  const [path, setPath] = useState('')
  const [issue, setIssue] = useState(sampleIssue)
  const [method, setMethod] = useState('bm25')
  const [tab, setTab] = useState<Tab>('overview')
  const [phase, setPhase] = useState<'idle' | 'indexing' | 'investigating'>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [duration, setDuration] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [guide, setGuide] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [copyStatus, setCopyStatus] = useState('')
  const [selectedPath, setSelectedPath] = useState('')
  const [snippet, setSnippet] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const busy = phase !== 'idle'
  const evidence = useMemo(() => (report ? collectEvidence(report.result) : []), [report])
  const files = [...new Set(evidence.map((e) => e.path))]
  const pathEvidence = evidence.filter((e) => e.path === selectedPath)
  const currentEvidence = pathEvidence[snippet] ?? pathEvidence[0]
  const failures = report?.result.tool_trace.filter((t) => toolError(t.output)).length ?? 0

  async function refreshWorkspace() {
    try {
      const data = await api<Workspace>('/workspace')
      setWorkspace(data)
      setConnected(true)
      setPath((current) => current || data.example_repository || data.allowed_root)
    } catch {
      setConnected(false)
    }
  }
  async function loadDemo() {
    setError('')
    try {
      const response = await fetch('/demo-report.json')
      if (!response.ok) throw new Error()
      const data = parseReport(await response.json())
      setReport(data)
      setSource('demo')
      setTab('overview')
      setDuration(null)
    } catch {
      setError('示例报告加载失败，请尝试导入已保存的 result.json。')
    }
  }
  useEffect(() => {
    void refreshWorkspace()
    void loadDemo()
  }, [])
  useEffect(() => {
    if (!busy) return
    const start = Date.now()
    setElapsed(0)
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - start) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [busy])
  useEffect(() => {
    setSelectedPath(
      report?.result.evidence_files.find((p) => evidence.some((e) => e.path === p)) ||
        evidence[0]?.path ||
        '',
    )
    setSnippet(0)
  }, [report, evidence])
  useEffect(() => {
    if (!guide && !exportOpen) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setGuide(false)
        setExportOpen(false)
      }
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [guide, exportOpen])

  async function importFile(file?: File) {
    if (!file) return
    setError('')
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('报告超过 5 MB，请选择较小的单次调查结果。')
      let input: unknown
      try {
        input = JSON.parse(await file.text())
      } catch {
        throw new Error('无法读取 JSON。请直接选择脚本生成的 result.json 文件。')
      }
      const data = parseReport(input)
      setReport(data)
      setSource('import')
      setIssue(data.result.issue_text)
      setDuration(null)
      setTab('overview')
    } catch (e) {
      setError(e instanceof Error ? e.message : '报告导入失败。')
    }
    if (fileInput.current) fileInput.current.value = ''
  }
  async function investigate() {
    if (!path.trim() || !issue.trim()) {
      setError('请填写本地仓库路径和问题描述。')
      return
    }
    setError('')
    setReport(null)
    setDuration(null)
    setSource('live')
    setTab('overview')
    setPhase('indexing')
    const start = Date.now()
    try {
      const indexed = indexSchema.parse(
        await api<IndexSummary>('/repositories/index', { path: path.trim() }),
      )
      setPhase('investigating')
      const result = await api<unknown>('/investigate', {
        issue_text: issue.trim(),
        method,
        response_language: 'zh',
      })
      setReport(parseReport({ index: indexed, result }))
      setDuration((Date.now() - start) / 1000)
    } catch (e) {
      setError(e instanceof Error ? e.message : '调查失败，请重试。')
    } finally {
      setPhase('idle')
    }
  }
  async function copyReport() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2))
      setCopyStatus('已复制完整报告，可粘贴到文本文件并保存为 .json。')
    } catch {
      setCopyStatus('浏览器未允许自动复制。请选中下方文本后按 Ctrl+A、Ctrl+C 复制。')
    }
  }
  function exportReport() {
    if (!report) return
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
    )
    const a = document.createElement('a')
    a.href = url
    a.download = `repopilot-${report.index?.repository ?? 'report'}.json`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
  }
  function showFile(name: string) {
    setSelectedPath(name)
    setSnippet(0)
    setTab('code')
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" inert={guide || exportOpen}>
        <a className="brand" href="/">
          <span className="brand-mark">
            <GitBranch size={23} />
          </span>
          <span>
            RepoPilot<small>CODE INVESTIGATION</small>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <button
          className="side-item active"
          onClick={() => {
            setTab('overview')
            setGuide(false)
          }}
        >
          <Layers size={18} />
          调查工作台
          <span className="side-dot" />
        </button>
        <button className="side-item" onClick={() => setGuide(true)}>
          <BookOpen size={18} />
          使用指南
          <ChevronRight size={15} />
        </button>
        <div className="sidebar-note">
          <div className="note-orbit">
            <Waypoints size={25} />
          </div>
          <strong>让每个判断，都有迹可循。</strong>
          <p>从问题出发，沿着代码证据，逐步理解可能的原因。</p>
          <span>检索 → 阅读 → 假设 → 验证</span>
        </div>
        <div className="sidebar-bottom">
          <span className="privacy-icon">
            <ShieldCheck size={17} />
          </span>
          <div>
            本地代码工作区<small>只读分析 · 不会修改仓库</small>
          </div>
        </div>
        <div className="version">
          RepoPilot v0.9 <span>实验性项目</span>
        </div>
      </aside>

      <div className="main-shell" inert={guide || exportOpen}>
        <header className="topbar">
          <div className="breadcrumb">
            <FolderGit2 size={16} />
            工作区<span>/</span>
            <strong>代码调查</strong>
          </div>
          <div className="topbar-actions">
            <button
              className={`connection ${connected ? 'online' : ''}`}
              onClick={() => void refreshWorkspace()}
              title="点击重新检测后端连接"
            >
              <i />
              {connected ? '后端已连接' : '离线查看模式'}
            </button>
            <button
              className="button subtle"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={15} />
              导入报告
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".json,application/json"
              aria-label="选择 JSON 报告"
              disabled={busy}
              className="visually-hidden"
              onChange={(event) => void importFile(event.target.files?.[0])}
            />
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">REPOSITORY INTELLIGENCE</div>
              <h1>
                代码调查工作台<span className="heading-dot">.</span>
              </h1>
              <p>读懂问题、追踪证据，让调查结果变得清晰可见。</p>
            </div>
            <button className="button secondary" disabled={busy} onClick={() => void loadDemo()}>
              <Play size={14} />
              查看示例
            </button>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="关闭错误提示" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          <div className="workbench">
            <section className="input-panel card">
              <div className="section-title">
                <span className="icon-box">
                  <Search size={17} />
                </span>
                <div>
                  <h2>发起一次调查</h2>
                  <p>提供仓库与问题，收集相关证据</p>
                </div>
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void investigate()
                }}
              >
                <label htmlFor="repository">
                  <span className="step-number">01</span>本地仓库
                </label>
                <div className="input-wrap">
                  <FolderGit2 size={16} />
                  <input
                    id="repository"
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                    disabled={busy}
                    placeholder="/absolute/path/to/repository"
                    required
                  />
                </div>
                <div className="field-helper">
                  填写后端所在电脑上的文件夹绝对路径。
                  {workspace?.example_repository && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setPath(workspace.example_repository!)
                        setIssue(sampleIssue)
                      }}
                    >
                      填入示例仓库 <ArrowRight size={12} />
                    </button>
                  )}
                </div>
                <label htmlFor="issue">
                  <span className="step-number">02</span>问题描述
                  <span className="optional">Issue / Bug report</span>
                </label>
                <textarea
                  id="issue"
                  value={issue}
                  onChange={(e) => setIssue(e.target.value)}
                  disabled={busy}
                  maxLength={4000}
                  rows={7}
                  required
                  placeholder="描述遇到的问题、预期行为和相关函数名…"
                />
                <div className="textarea-footer">
                  <span>保留函数名或英文 Issue 有助于检索</span>
                  <span>{issue.length}/4000</span>
                </div>
                <label htmlFor="method">
                  <span className="step-number">03</span>检索方式
                </label>
                <div className="select-wrap">
                  <select
                    id="method"
                    value={method}
                    disabled={busy}
                    onChange={(e) => setMethod(e.target.value)}
                  >
                    {(workspace?.methods ?? ['bm25', 'keyword']).map((m) => (
                      <option key={m} value={m}>
                        {methodNames[m] ?? m}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={16} />
                </div>
                <div className="model-info">
                  <span>
                    <Sparkles size={14} />
                    调查模型
                  </span>
                  <strong>{workspace?.model ?? '等待后端配置'}</strong>
                </div>
                <button
                  className="button primary run-button"
                  type="submit"
                  disabled={busy || !connected || !workspace?.investigation_configured}
                >
                  {busy ? <LoaderCircle className="spin" size={17} /> : <Play size={16} />}
                  {busy ? '正在调查…' : '开始调查'}
                  {!busy && <ArrowRight size={16} />}
                </button>
                {!connected && (
                  <p className="run-help">启动后端即可发起新调查，也可以先导入已有报告。</p>
                )}
                {connected && !workspace?.investigation_configured && (
                  <p className="run-help">后端未配置模型，请使用完整工作台启动脚本。</p>
                )}
                <p className="local-caption">
                  <ShieldCheck size={12} />
                  只读工具 · 不执行目标代码 · 结论需复核
                </p>
              </form>
              <button className="help-link" onClick={() => setGuide(true)}>
                <HelpCircle size={15} />
                第一次使用？了解结果怎么看
                <ChevronRight size={14} />
              </button>
            </section>

            <section className="report-area" aria-live="polite" aria-busy={busy}>
              {busy ? (
                <div className="card progress-card">
                  <div className="progress-orbit">
                    <Search size={34} />
                    <span />
                  </div>
                  <span className="eyebrow">INVESTIGATION IN PROGRESS</span>
                  <h2>{phase === 'indexing' ? '正在建立代码索引' : '正在阅读代码与调查问题'}</h2>
                  <p>
                    {phase === 'indexing'
                      ? '扫描仓库文件，提取函数、类和代码片段。'
                      : '模型正在调用只读工具。完成后会展示真实调用记录。'}
                  </p>
                  <div className="progress-steps">
                    <span className={phase === 'investigating' ? 'done' : 'running'}>
                      {phase === 'investigating' ? (
                        <Check size={15} />
                      ) : (
                        <LoaderCircle size={15} className="spin" />
                      )}
                      建立索引
                    </span>
                    <i />
                    <span className={phase === 'investigating' ? 'running' : ''}>
                      <Activity size={15} />
                      模型调查
                    </span>
                    <i />
                    <span>
                      <FileJson size={15} />
                      生成报告
                    </span>
                  </div>
                  <span className="elapsed">已等待 {elapsed} 秒 · 耗时取决于仓库大小与模型</span>
                </div>
              ) : report ? (
                <>
                  <div className="report-heading">
                    <div>
                      <span className={`report-source ${source === 'live' ? 'live' : ''}`}>
                        {source === 'demo'
                          ? '示例报告 · 历史运行'
                          : source === 'import'
                            ? '已导入的报告'
                            : '本次实时调查'}
                      </span>
                      <h2>
                        {report.index?.repository ?? '调查结果'}
                        <span>调查报告</span>
                      </h2>
                    </div>
                    <button
                      className="icon-button"
                      title="导出 JSON 报告"
                      aria-label="导出 JSON 报告"
                      onClick={() => {
                        setCopyStatus('')
                        setExportOpen(true)
                      }}
                    >
                      <ArrowDownToLine size={18} />
                    </button>
                  </div>
                  <div className="metrics">
                    <div>
                      <Files size={18} />
                      <strong>{files.length}</strong>
                      <span>已观察文件</span>
                    </div>
                    <div>
                      <Code2 size={18} />
                      <strong>{report.result.initial_context.retrieved_chunks.length}</strong>
                      <span>初始代码片段</span>
                    </div>
                    <div>
                      <Waypoints size={18} />
                      <strong>{report.result.tool_trace.length}</strong>
                      <span>工具调用</span>
                    </div>
                    <div>
                      <ListChecks size={18} />
                      <strong>{report.result.test_plan.length}</strong>
                      <span>建议测试</span>
                    </div>
                  </div>
                  <div className="card report-card">
                    <nav className="report-tabs" aria-label="报告视图">
                      {tabs.map((t) => (
                        <button
                          className={tab === t.id ? 'selected' : ''}
                          key={t.id}
                          onClick={() => setTab(t.id)}
                        >
                          <t.icon size={16} />
                          {t.label}
                          {t.id === 'trace' && failures > 0 && (
                            <i className="warning-count">{failures}</i>
                          )}
                        </button>
                      ))}
                    </nav>
                    <div className="report-body">
                      {tab === 'overview' && (
                        <>
                          <div
                            className={`status-row ${report.result.status === 'incomplete' ? 'warning' : ''}`}
                          >
                            <span>
                              {report.result.status === 'complete' ? (
                                <CheckCircle2 size={17} />
                              ) : (
                                <AlertTriangle size={17} />
                              )}
                              {report.result.status === 'complete'
                                ? '调查流程已完成'
                                : '调查未完整结束'}
                            </span>
                            {duration !== null && <small>{duration.toFixed(1)} 秒</small>}
                            <small>结论尚未验证</small>
                          </div>
                          {report.result.status === 'incomplete' && (
                            <div className="incomplete-box">
                              <strong>{explainFailure(report.result.limitation)}</strong>
                              <p>{report.result.limitation}</p>
                            </div>
                          )}
                          <section
                            className={`evidence-assessment ${report.result.evidence_status}`}
                            aria-label="证据检查"
                          >
                            <div className="subheading">
                              <span>
                                <ShieldCheck size={16} />
                                证据检查
                              </span>
                              <em>
                                {report.result.evidence_status === 'verified'
                                  ? '引用范围已核对'
                                  : report.result.evidence_status === 'insufficient'
                                    ? '证据不足 · 需要复核'
                                    : '尚未完成检查'}
                              </em>
                            </div>
                            <p>
                              {report.result.evidence_status === 'verified'
                                ? '引用行号均来自模型实际读到的源码。这里只核对证据来源，不代表根因判断正确。'
                                : report.result.evidence_status === 'insufficient'
                                  ? '这份报告已返回，但部分依据未通过检查，请先复核下列问题。'
                                  : '旧报告或未完成的调查没有可用的逐行检查结果。'}
                            </p>
                            {report.result.evidence_checks.length > 0 && (
                              <ul>
                                {report.result.evidence_checks.map((code) => (
                                  <li key={code}>{explainEvidenceCheck(code)}</li>
                                ))}
                              </ul>
                            )}
                          </section>
                          {source === 'live' &&
                            report.result.root_cause_hypothesis &&
                            !/[\u3400-\u9fff]/.test(report.result.root_cause_hypothesis) && (
                              <p className="language-note">
                                模型本次未遵循中文要求，以下保留其原文。
                              </p>
                            )}
                          <div className="hypothesis">
                            <div className="subheading">
                              <span>
                                <Sparkles size={16} />
                                根因假设
                              </span>
                              <em>模型生成</em>
                            </div>
                            <p>
                              {report.result.root_cause_hypothesis ??
                                '本次没有生成完整假设，请先查看已收集的代码证据与调用轨迹。'}
                            </p>
                            <div className="hypothesis-foot">
                              <ShieldCheck size={14} />
                              这是待验证的解释，不表示问题已经被修复。
                            </div>
                          </div>
                          {report.result.synthesis_note && (
                            <p className="language-note">{report.result.synthesis_note}</p>
                          )}
                          {report.result.draft_output_text && (
                            <details className="original-answer">
                              <summary>查看证据整理前的模型初稿</summary>
                              <pre>{report.result.draft_output_text}</pre>
                            </details>
                          )}
                          {report.result.translation_note && (
                            <p className="language-note">{report.result.translation_note}</p>
                          )}
                          {report.result.original_output_text && (
                            <details className="original-answer">
                              <summary>对照模型原始回答</summary>
                              <pre>{report.result.original_output_text}</pre>
                            </details>
                          )}
                          {source === 'demo' && (
                            <div className="explainer">
                              <div className="subheading">
                                <span>
                                  <BookOpen size={16} />
                                  这份结果，用人话怎么理解？
                                </span>
                                <em>示例人工讲解</em>
                              </div>
                              <p>
                                名字为空时，校验函数返回 <code>False</code>，但启动函数
                                <strong>没有处理这个返回值</strong>
                                。就像检查员说“不合格”，后面的流程却照常继续。
                              </p>
                              <p className="explainer-note">
                                模型只读了校验函数，未充分检查调用方，所以它的解释还不够准确。应进一步查看{' '}
                                <code>mcp_server.py</code>
                                ，并测试“空名字时应阻止启动”。这段讲解仅针对示例，不是模型自动得出的结论。
                              </p>
                            </div>
                          )}
                          {report.result.citations.length > 0 && (
                            <section className="citation-list" aria-label="具体代码引用">
                              <h3>具体代码引用</h3>
                              {report.result.citations.map((citation, i) => (
                                <details
                                  key={i}
                                  className={
                                    citation.verified ? 'citation verified' : 'citation unverified'
                                  }
                                >
                                  <summary>
                                    <FileCode2 size={14} />
                                    <span>
                                      {citation.file_path}:L{citation.start_line}–
                                      {citation.end_line}
                                    </span>
                                    <small>{citation.verified ? '已读到' : '未通过检查'}</small>
                                  </summary>
                                  <p>{citation.reason}</p>
                                  {citation.problems.length > 0 && (
                                    <ul>
                                      {citation.problems.map((problem) => (
                                        <li key={problem}>{explainEvidenceCheck(problem)}</li>
                                      ))}
                                    </ul>
                                  )}
                                  {citation.content && (
                                    <CodeBlock
                                      evidence={{
                                        path: citation.file_path,
                                        symbol: '引用',
                                        start: citation.start_line,
                                        end: citation.end_line,
                                        content: citation.content,
                                        origin: '具体引用',
                                      }}
                                    />
                                  )}
                                </details>
                              ))}
                            </section>
                          )}
                          {report.result.uncertainties.length > 0 && (
                            <section className="uncertainties">
                              <h3>尚待确认</h3>
                              <ul>
                                {report.result.uncertainties.map((item, i) => (
                                  <li key={i}>{item}</li>
                                ))}
                              </ul>
                            </section>
                          )}
                          <div className="subheading section-gap">
                            <span>
                              <FileCode2 size={16} />
                              模型引用的文件
                            </span>
                            <small>文件被看过 ≠ 因果已证实</small>
                          </div>
                          <div className="file-chips">
                            {report.result.evidence_files.length ? (
                              report.result.evidence_files.map((f) => (
                                <button key={f} onClick={() => showFile(f)}>
                                  <FileCode2 size={14} />
                                  {f}
                                  <ChevronRight size={14} />
                                </button>
                              ))
                            ) : (
                              <span className="muted">暂无可接受的文件引用。</span>
                            )}
                          </div>
                          <div className="subheading section-gap">
                            <span>
                              <GitBranch size={16} />
                              建议的下一步
                            </span>
                          </div>
                          <ol className="step-list">
                            {report.result.investigation_steps.map((step, i) => (
                              <li key={i}>
                                <span>{String(i + 1).padStart(2, '0')}</span>
                                <p>{step}</p>
                              </li>
                            ))}
                          </ol>
                          <details className="issue-details">
                            <summary>
                              查看这份报告对应的问题描述
                              <ChevronDown size={14} />
                            </summary>
                            <p>{report.result.issue_text}</p>
                          </details>
                        </>
                      )}
                      {tab === 'code' && (
                        <>
                          <div className="view-intro">
                            <h3>每一条证据，都能回到代码</h3>
                            <p>查看初始检索和工具实际读取的片段。相关性分数不是正确率。</p>
                          </div>
                          {files.length ? (
                            <div className="evidence-layout">
                              <div className="file-list">
                                {files.map((f) => (
                                  <button
                                    className={selectedPath === f ? 'selected' : ''}
                                    key={f}
                                    onClick={() => {
                                      setSelectedPath(f)
                                      setSnippet(0)
                                    }}
                                  >
                                    <FileCode2 size={15} />
                                    <span>{f}</span>
                                    <small>{evidence.filter((e) => e.path === f).length}</small>
                                  </button>
                                ))}
                              </div>
                              <div className="evidence-content">
                                {currentEvidence ? (
                                  <>
                                    <div className="snippet-picker">
                                      <label htmlFor="snippet">代码片段</label>
                                      <select
                                        id="snippet"
                                        value={snippet}
                                        onChange={(e) => setSnippet(Number(e.target.value))}
                                      >
                                        {pathEvidence.map((item, i) => (
                                          <option key={i} value={i}>
                                            {item.origin} · {item.symbol} · L{item.start}–{item.end}
                                          </option>
                                        ))}
                                      </select>
                                    </div>
                                    <CodeBlock evidence={currentEvidence} />
                                  </>
                                ) : (
                                  <p>报告中没有该文件的可展示片段。</p>
                                )}
                              </div>
                            </div>
                          ) : (
                            <p className="empty-message">本次没有收集到可展示的代码。</p>
                          )}
                        </>
                      )}
                      {tab === 'trace' && (
                        <>
                          <div className="view-intro">
                            <h3>模型是怎样调查的？</h3>
                            <p>按实际发生顺序记录，展开任意一步查看参数和返回内容。</p>
                          </div>
                          {report.result.tool_trace.length ? (
                            <div className="timeline">
                              {report.result.tool_trace.map((tool, i) => {
                                const failed = toolError(tool.output)
                                return (
                                  <details
                                    key={i}
                                    className={`timeline-item ${failed ? 'failed' : ''}`}
                                  >
                                    <summary>
                                      <span className="timeline-node">
                                        {String(i + 1).padStart(2, '0')}
                                      </span>
                                      <div>
                                        <strong>
                                          {toolNames[tool.name] ?? tool.name}
                                          <span className="tool-state">
                                            {failed ? '调用失败' : '已返回'}
                                          </span>
                                        </strong>
                                        <p>
                                          {String(
                                            tool.arguments.path ??
                                              tool.arguments.query ??
                                              tool.arguments.name ??
                                              '参数解析失败',
                                          )}
                                        </p>
                                      </div>
                                      <ChevronDown size={16} />
                                    </summary>
                                    <div className="timeline-content">
                                      <div className="argument-pills">
                                        {Object.entries(tool.arguments).map(([key, value]) => (
                                          <span key={key}>
                                            {key}
                                            <b>
                                              {typeof value === 'object'
                                                ? JSON.stringify(value)
                                                : String(value)}
                                            </b>
                                          </span>
                                        ))}
                                      </div>
                                      <ToolDetails output={tool.output} />
                                    </div>
                                  </details>
                                )
                              })}
                            </div>
                          ) : (
                            <p className="empty-message">
                              本次没有实际工具调用。请勿将初始检索当作工具调用。
                            </p>
                          )}
                        </>
                      )}
                      {tab === 'tests' && (
                        <>
                          <div className="view-intro">
                            <h3>用测试，把假设变成证据</h3>
                            <p>以下是模型建议，尚未执行。需要检查方案本身是否合理。</p>
                          </div>
                          <div className="test-cards">
                            {report.result.test_plan.map((plan, i) => (
                              <article key={i}>
                                <span className="test-number">
                                  {String(i + 1).padStart(2, '0')}
                                </span>
                                <div>
                                  <span className="pending-label">待人工验证</span>
                                  <p>{plan}</p>
                                </div>
                              </article>
                            ))}
                          </div>
                          {report.result.test_plan.length === 0 && (
                            <p className="empty-message">本次没有生成测试建议。</p>
                          )}
                          <div className="verification-note">
                            <Terminal size={18} />
                            <p>
                              RepoPilot
                              不会自动运行目标仓库的测试。执行前请先确认测试环境与预期行为。
                            </p>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="report-footer">
                    <ShieldCheck size={13} />
                    <span>
                      {report.index
                        ? `已索引 ${report.index.files_indexed} 个文件 · ${report.index.chunks_created} 个片段`
                        : '导入报告未包含索引统计'}
                    </span>
                    <span>结果仅供调查参考</span>
                  </div>
                </>
              ) : (
                <div className="card empty-card">
                  <FolderGit2 size={40} />
                  <h2>从一份问题描述开始</h2>
                  <p>选择左侧仓库发起调查，或导入你已经运行过的 JSON 报告。</p>
                  <button className="button secondary" onClick={() => void loadDemo()}>
                    先看看示例
                    <ArrowRight size={15} />
                  </button>
                </div>
              )}
            </section>
          </div>
        </main>
      </div>
      {exportOpen && report && (
        <div className="modal-backdrop" onClick={() => setExportOpen(false)}>
          <section
            className="guide-modal"
            role="dialog"
            aria-modal="true"
            aria-label="导出报告"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              autoFocus
              aria-label="关闭导出报告"
              onClick={() => setExportOpen(false)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">SAVE REPORT</span>
            <h2>保存这次调查</h2>
            <p className="muted">
              下载 JSON 文件，或复制完整报告后保存为 .json，下次可通过“导入报告”继续查看。
            </p>
            <div className="export-actions">
              <button className="button primary" onClick={exportReport}>
                <ArrowDownToLine size={16} />
                下载 JSON
              </button>
              <button className="button secondary" onClick={() => void copyReport()}>
                <FileJson size={16} />
                复制完整报告
              </button>
            </div>
            <p className="export-status" role="status">
              {copyStatus || '如果浏览器没有弹出下载，请使用复制按钮或选中下方文本。'}
            </p>
            <textarea
              className="export-json"
              aria-label="完整 JSON 报告"
              readOnly
              value={JSON.stringify(report, null, 2)}
            />
          </section>
        </div>
      )}
      {guide && (
        <div className="modal-backdrop" onClick={() => setGuide(false)}>
          <section
            className="guide-modal"
            role="dialog"
            aria-modal="true"
            aria-label="使用指南"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              autoFocus
              aria-label="关闭使用指南"
              onClick={() => setGuide(false)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">QUICK GUIDE</span>
            <h2>一份报告，四个阅读角度</h2>
            <p className="muted">先看解释，再看依据，最后决定怎么验证。</p>
            <ol className="guide-list">
              <li>
                <BookOpen />
                <div>
                  <strong>调查摘要</strong>
                  <p>模型认为哪里可能出问题。“流程已完成”只说明成功返回了报告。</p>
                </div>
              </li>
              <li>
                <Code2 />
                <div>
                  <strong>代码证据</strong>
                  <p>查看它实际见过的文件、函数和行号，判断假设是否有源码支持。</p>
                </div>
              </li>
              <li>
                <Waypoints />
                <div>
                  <strong>调用轨迹</strong>
                  <p>检查模型搜索、读取、重试的过程。失败的工具调用也会如实显示。</p>
                </div>
              </li>
              <li>
                <ListChecks />
                <div>
                  <strong>验证计划</strong>
                  <p>看接下来应该做哪些测试。这些是建议，不是已通过的测试。</p>
                </div>
              </li>
            </ol>
            <div className="guide-tip">
              <Upload size={17} />
              <span>
                已有结果？点击右上角“导入报告”，选择 <code>demo-output/result.json</code>
                。文件只在浏览器中读取，不会上传。
              </span>
            </div>
            <button className="button primary" onClick={() => setGuide(false)}>
              明白了，开始查看
              <ArrowRight size={16} />
            </button>
          </section>
        </div>
      )}
    </div>
  )
}
