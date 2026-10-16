/// <reference types="vite/client" />

import type { CoreDraft } from '../api/core.generated'

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

export function core1Example(name: string): CoreDraft {
  const document = Object.entries(documents).find(([path]) => path.endsWith(`/${name}.json`))?.[1]
  if (!document) throw new Error(`未找到 core-1 示例：${name}`)
  return structuredClone(document.draft)
}
