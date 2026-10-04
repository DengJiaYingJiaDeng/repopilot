import { describe, expect, it } from 'vitest'
import sample from '../public/demo-report.json'
import { collectEvidence, explainFailure, parseReport, toolError } from './data'

describe('saved investigation reports', () => {
  it('accepts both CLI envelopes and raw API results', () => {
    expect(parseReport(sample).index?.repository).toBe('sample_repo')
    expect(parseReport(sample.result).result.issue_text).toBe(sample.result.issue_text)
  })
  it('rejects incomplete shapes before they reach rendering', () => {
    expect(() => parseReport({ result: { status: 'complete' } })).toThrow('文件格式不正确')
    expect(() => parseReport({ result: { ...sample.result, tool_trace: [null] } })).toThrow()
  })
  it('preserves failed tool calls and only extracts actual source evidence', () => {
    const report = parseReport(sample)
    const evidence = collectEvidence(report.result)
    expect(toolError(report.result.tool_trace[0].output)).toContain('Invalid source line range')
    expect(evidence.some((e) => e.content.includes('Invalid source line range'))).toBe(false)
    expect(evidence.some((e) => e.path === 'utils.py' && e.origin === '工具读取')).toBe(true)
    expect(
      evidence.filter((e) => e.origin === '工具读取').every((e) => !/^\d+:/.test(e.content)),
    ).toBe(true)
  })
  it('does not mistake arbitrary tool text for successful structured evidence', () => {
    const report = parseReport(sample)
    report.result.tool_trace = [{ name: 'read_file', arguments: {}, output: 'not JSON' }]
    expect(collectEvidence(report.result).every((e) => e.origin === '初始检索')).toBe(true)
    expect(toolError('not JSON')).toBeNull()
  })
  it('explains incomplete model results without claiming the bug was fixed', () => {
    expect(explainFailure('Tool call limit reached')).toContain('尚未形成完整结论')
    expect(explainFailure('Local model server is unavailable or timed out')).toContain('没有响应')
  })
})

it('keeps translated and original answers distinct on import', () => {
  const original = '{"root_cause_hypothesis":"An unverified English hypothesis"}'
  const report = parseReport({
    ...sample.result,
    original_output_text: original,
    translation_note: '中文转述由本地模型生成，原始回答已保留。',
  })
  expect(report.result.original_output_text).toBe(original)
  expect(report.result.translation_note).toContain('原始回答已保留')
})

it('preserves v2 evidence checks and never upgrades an old report', () => {
  expect(parseReport(sample).result.evidence_status).toBe('unchecked')
  const report = parseReport({
    ...sample.result,
    evidence_status: 'insufficient',
    evidence_checks: ['citation_not_read'],
    citations: [
      {
        file_path: 'utils.py',
        start_line: 4,
        end_line: 5,
        reason: 'unverified',
        verified: false,
        problems: ['citation_not_read'],
      },
    ],
    uncertainties: ['Caller not checked'],
    synthesis_note: 'Report assembled from reads',
    draft_output_text: 'old draft',
  })
  expect(report.result.citations[0].verified).toBe(false)
  expect(report.result.citations[0].content).toBe('')
  expect(report.result.evidence_checks).toEqual(['citation_not_read'])
  expect(report.result.uncertainties).toEqual(['Caller not checked'])
  expect(report.result.draft_output_text).toBe('old draft')
})
