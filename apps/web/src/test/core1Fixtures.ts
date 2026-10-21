/// <reference types="vite/client" />

import type { CoreDraft } from '../api/core.generated'
import type { Draft } from '../api/types'
// Document instances left core-1 for the instance store; the backend keeps the
// examples' instances in one fixture that both test suites read. A glob, like the
// examples above, so image builds that copy only apps/web still compile.
const instanceFiles = import.meta.glob<Record<string, unknown>>(
  '../../../api/tests/fixtures/document_instances.json',
  { eager: true, import: 'default' },
)
const instanceFixtures = Object.values(instanceFiles)[0] ?? {}

type ExampleInstances = Partial<Pick<Draft, 'material_objects' | 'material_links'>>

interface NativeExample {
  format: string
  schema_version: string
  draft: CoreDraft
}

const documents = import.meta.glob<NativeExample>(
  '../../../../docs/design/core-1-examples/*.json',
  { eager: true, import: 'default' },
)

export const core1ExampleNames = Object.keys(documents)
  .map((path) => path.split('/').pop()!.replace(/\.json$/, ''))
  .sort()

export function core1Example(name: string): CoreDraft & ExampleInstances {
  const document = Object.entries(documents).find(([path]) => path.endsWith(`/${name}.json`))?.[1]
  if (!document) throw new Error(`未找到 core-1 示例：${name}`)
  const instances = (instanceFixtures as unknown as Record<string, ExampleInstances>)[name] ?? {}
  return structuredClone({ ...document.draft, ...instances })
}
