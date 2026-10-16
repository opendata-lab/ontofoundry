import { describe, expect, it } from 'vitest'
import { core1Example, core1ExampleNames } from './core1Fixtures'

describe('core-1 shared design fixtures', () => {
  it('loads all thirteen examples without replacing UUIDs or expressions', () => {
    expect(core1ExampleNames).toHaveLength(13)
    for (const name of core1ExampleNames) {
      const draft = core1Example(name)
      expect(draft.schema_version).toBe('core-1')
      expect(draft.workspace_id).toMatch(/^[0-9a-f-]{36}$/)
    }
    const draft = core1Example('13-dataset-metrics')
    expect(draft.object_types).toEqual([])
    const metric = draft.metrics?.find((item) => item.kind === 'expression')
    expect(metric?.kind === 'expression' && metric.expression).toContain('code_lines_daily.commit_count')
  })

  it('returns independent drafts for editor fixtures', () => {
    const draft = core1Example('01-basic-sales')
    draft.object_types?.pop()
    expect(core1Example('01-basic-sales').object_types).toHaveLength(2)
  })
})
