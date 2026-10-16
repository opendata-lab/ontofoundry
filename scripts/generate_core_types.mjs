import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const schemaPath = join(root, 'apps/api/src/ontofoundry_api/contracts/ontofoundry.core-1.schema.json')
const target = join(root, 'apps/web/src/api/core.generated.ts')
const schema = JSON.parse(await readFile(schemaPath, 'utf8'))
const output = await compile(schema, 'CoreDraft', {
  bannerComment: '/* Generated from the core-1 Pydantic schema. Do not edit by hand. */',
  additionalProperties: false,
  style: { singleQuote: true, semi: false },
})
if (process.argv.includes('--check')) {
  const temporary = await mkdtemp(join(tmpdir(), 'ontofoundry-core-types-'))
  try {
    const generated = join(temporary, 'core.generated.ts')
    await writeFile(generated, output)
    const current = await readFile(target, 'utf8').catch(() => '')
    if (current !== await readFile(generated, 'utf8')) {
      console.error('core-1 TS 类型已漂移，请运行 generate:core-types')
      process.exitCode = 1
    } else {
      console.log('core-1 TS 类型与 schema 一致')
    }
  } finally {
    await rm(temporary, { recursive: true, force: true })
  }
} else {
  await writeFile(target, output)
  console.log(target)
}
