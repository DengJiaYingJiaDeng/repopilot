import { z } from 'zod'

const chunkSchema = z
  .object({
    file_path: z.string(),
    symbol_name: z.string().nullable(),
    content: z.string(),
    start_line: z.number(),
    end_line: z.number(),
  })
  .passthrough()
const contextSchema = z.object({
  query: z.string(),
  relevant_files: z.array(z.string()),
  relevant_symbols: z.array(z.string()),
  retrieved_chunks: z.array(z.object({ chunk: chunkSchema, score: z.number() })),
})
const resultSchema = z.object({
  issue_text: z.string(),
  status: z.enum(['complete', 'incomplete']),
  initial_context: contextSchema,
  root_cause_hypothesis: z.string().nullable().optional(),
  investigation_steps: z.array(z.string()).default([]),
  test_plan: z.array(z.string()).default([]),
  evidence_files: z.array(z.string()).default([]),
  tool_trace: z
    .array(
      z.object({
        name: z.string(),
        arguments: z.record(z.string(), z.unknown()),
        output: z.string(),
      }),
    )
    .default([]),
  limitation: z.string().nullable().optional(),
  review_required: z.boolean().default(false),
  original_output_text: z.string().nullable().optional(),
  translation_note: z.string().nullable().optional(),
})
export const indexSchema = z.object({
  repository: z.string(),
  files_indexed: z.number(),
  chunks_created: z.number(),
  skipped_files: z.array(z.string()),
})
export type IndexSummary = z.infer<typeof indexSchema>
export type Investigation = z.infer<typeof resultSchema>
export type Report = { index?: IndexSummary; result: Investigation }
export type Workspace = {
  allowed_root: string
  example_repository: string | null
  methods: string[]
  model: string | null
  provider: string
  investigation_configured: boolean
}
export type Evidence = {
  path: string
  symbol: string
  start: number
  end: number
  content: string
  origin: string
  score?: number
  truncated?: boolean
}

export function parseReport(input: unknown): Report {
  const envelope = z
    .object({ index: indexSchema.optional(), result: resultSchema })
    .safeParse(input)
  if (envelope.success) return envelope.data
  const raw = resultSchema.safeParse(input)
  if (raw.success) return { result: raw.data }
  throw new Error('文件格式不正确。请选择演示生成的 result.json，或 /investigate 的完整响应。')
}

export function toolOutput(output: string): unknown {
  try {
    return JSON.parse(output)
  } catch {
    return output
  }
}
export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
export function toolError(output: string): string | null {
  const parsed = toolOutput(output)
  return isRecord(parsed) && typeof parsed.error === 'string' ? parsed.error : null
}
export function collectEvidence(result: Investigation): Evidence[] {
  const evidence: Evidence[] = result.initial_context.retrieved_chunks.map(({ chunk, score }) => ({
    path: chunk.file_path,
    symbol: chunk.symbol_name ?? 'module',
    start: chunk.start_line,
    end: chunk.end_line,
    content: chunk.content,
    score,
    origin: '初始检索',
  }))
  for (const tool of result.tool_trace) {
    const parsed = toolOutput(tool.output)
    const items = Array.isArray(parsed) ? parsed : [parsed]
    for (const item of items) {
      if (
        !isRecord(item) ||
        typeof item.file_path !== 'string' ||
        typeof item.content !== 'string' ||
        'error' in item
      )
        continue
      evidence.push({
        path: item.file_path,
        symbol: typeof item.symbol === 'string' ? item.symbol : '文件片段',
        start: typeof item.start_line === 'number' ? item.start_line : 1,
        end: typeof item.end_line === 'number' ? item.end_line : 1,
        content: tool.name === 'read_file' ? item.content.replace(/^\d+: ?/gm, '') : item.content,
        origin: tool.name === 'read_file' ? '工具读取' : '工具检索',
        truncated: item.content_truncated === true,
      })
    }
  }
  return [...new Map(evidence.map((e) => [`${e.path}:${e.start}:${e.content}`, e])).values()]
}

export function explainFailure(message?: string | null): string {
  if (!message) return '请检查已有证据，再决定下一步。'
  if (message.includes('Tool call limit'))
    return '模型用完了工具调用次数，尚未形成完整结论。可以缩小问题范围后重试。'
  if (message.includes('unavailable') || message.includes('timed out'))
    return '本地模型没有响应，请确认模型服务已启动。'
  if (message.includes('token limit')) return '模型输出过长，本次调查已停止。已有工具记录仍可查看。'
  if (message.includes('JSON schema')) return '模型没有按要求返回结构化结论。已有代码证据仍然保留。'
  if (message.includes('absent from observed evidence'))
    return '模型引用了未观察到的文件，系统拒绝了这份结论。'
  if (message.includes('HTTP 400'))
    return '模型服务拒绝了请求，可能是上下文超出限制。请检查模型服务日志。'
  return '调查未完整结束。下方保留了后端给出的原因和已经收集的证据。'
}

const apiBase =
  (import.meta as ImportMeta & { env: Record<string, string> }).env.VITE_API_BASE_URL ||
  'http://127.0.0.1:8000'
export async function api<T>(path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(
      `${apiBase}${path}`,
      body === undefined
        ? {}
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
    )
  } catch {
    throw new Error('连接不到后端服务。请用一键启动脚本启动工作台；已保存的报告仍可导入查看。')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? '')
    if (response.status === 503)
      throw new Error('尚未配置调查模型。请使用带本地模型的一键启动脚本。')
    if (response.status === 422) throw new Error('输入格式不正确，请检查仓库路径与问题描述。')
    throw new Error(`请求失败（${response.status}）：${detail}`)
  }
  return data as T
}
