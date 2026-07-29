/**
 * Any2PPT 的隔离 Slidev 渲染服务。
 *
 * 后端只准备 job 目录和业务数据，本进程负责白名单主题安装/缓存、主题布局
 * 能力扫描、PPTX 导出与 PNG 预览。所有外部 ID 和路径都经过校验，避免通过
 * 渲染接口读取或覆盖 renderRoot/themeRoot 之外的文件。
 */

import { execFile } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import { createServer } from 'node:http'
import { access, cp, mkdir, readFile, readdir, rename, rm, symlink, unlink, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const renderRoot = path.resolve(process.env.RENDER_ROOT || '/data/render_jobs')
const themeRoot = path.resolve(process.env.THEME_ROOT || '/data/themes')
const packageRoot = path.join(themeRoot, 'packages')
const npmCacheRoot = path.join(themeRoot, '.npm-cache')
const slidevBin = '/app/node_modules/.bin/slidev'
const installs = new Map()
const capabilitySchemaVersion = 2
const allowedThemes = new Set([
  '@slidev/theme-default@0.25.0',
  '@slidev/theme-seriph@0.25.0',
  '@slidev/theme-apple-basic@0.25.1',
  '@slidev/theme-bricks@0.25.0',
  'slidev-theme-tahta@0.13.2',
  'slidev-theme-academic@3.0.1',
  'slidev-theme-dracula@0.2.5',
  'slidev-theme-neversink@0.4.1',
  'slidev-theme-nord@0.0.6',
  'slidev-theme-light-icons@1.0.2',
  '@slidev/theme-shibainu@0.25.0',
  'slidev-theme-flayyer@1.0.2',
  'slidev-theme-eloc@1.1.0',
  'slidev-theme-purplin@1.2.0',
  'slidev-theme-unicorn@1.1.2',
  'slidev-theme-zhozhoba@1.0.0',
  'slidev-theme-penguin@2.3.1',
  'slidev-theme-vuetiful@0.3.1',
  'slidev-theme-nearform@3.0.0',
  '@timdaik/slidev-theme-nutmeg@0.5.0',
  '@enyineer/slidev-theme-neocarbon@1.0.8',
  'slidev-theme-geist@0.8.1',
  'slidev-theme-frankfurt@1.0.9',
])

function json(response, status, payload) {
  // 所有 endpoint 使用同一 JSON 响应格式，调用方无需猜 content-type。
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
  response.end(JSON.stringify(payload))
}

async function readJson(request) {
  // 限制控制请求体；课件正文通过共享 job 目录传递，不走这个 HTTP body。
  let body = ''
  for await (const chunk of request) {
    body += chunk
    if (body.length > 64 * 1024) throw new Error('REQUEST_TOO_LARGE')
  }
  return JSON.parse(body || '{}')
}

function validatedTheme(payload) {
  // 只允许目录中审查过的固定版本，防止任意 npm 包安装与供应链执行。
  const themeSpec = `${payload.theme_package}@${payload.theme_version}`
  if (!allowedThemes.has(themeSpec)) throw new Error('THEME_NOT_ALLOWED')
  return themeSpec
}

function projectThemeDir(projectId) {
  // UUID 校验与 resolve 前缀检查共同阻止目录穿越。
  if (!/^[0-9a-f-]{36}$/i.test(projectId || '')) throw new Error('INVALID_PROJECT_ID')
  const target = path.resolve(themeRoot, projectId)
  if (!target.startsWith(`${themeRoot}${path.sep}`)) throw new Error('INVALID_THEME_PATH')
  return target
}

function packageCacheKey(themeSpec) {
  // 包名可能含 @ 和 /，哈希后才能稳定作为缓存目录。
  return createHash('sha256').update(themeSpec).digest('hex').slice(0, 24)
}

function packageThemeDir(themeSpec) {
  return path.join(packageRoot, packageCacheKey(themeSpec))
}

function themePackageName(themeSpec) {
  if (themeSpec.startsWith('@')) {
    const separator = themeSpec.lastIndexOf('@')
    return themeSpec.slice(0, separator)
  }
  return themeSpec.slice(0, themeSpec.lastIndexOf('@'))
}

function themePackageDir(nodeModules, themeSpec) {
  const packageName = themePackageName(themeSpec)
  const target = path.resolve(nodeModules, ...packageName.split('/'))
  if (!target.startsWith(`${path.resolve(nodeModules)}${path.sep}`)) throw new Error('INVALID_THEME_PACKAGE_PATH')
  return target
}

function extractProps(source) {
  // 从主题 layout 源码中提取可传属性；这里只做能力提示，不执行源码。
  const body = source.match(/defineProps\(\s*\{([\s\S]*?)^\}\s*\)/m)?.[1] || ''
  const props = []
  for (const match of body.matchAll(/^\s*['"]?([A-Za-z_$][\w$-]*)['"]?\s*:\s*\{/gm)) {
    if (!props.includes(match[1])) props.push(match[1])
  }
  return props
}

function extractSlots(source) {
  // 命名 slot 决定生成器应使用的 ::slot:: Markdown 区域。
  const slots = []
  for (const match of source.matchAll(/<slot(?:\s+[^>]*?\bname=["']([^"']+)["'])?[^>]*>/g)) {
    const name = match[1] || 'default'
    if (!slots.includes(name)) slots.push(name)
  }
  return slots.length ? slots : ['default']
}

function layoutUsage(name, slots) {
  // 把主题作者的英文 layout 名转成生成模型可理解的中文语义。
  if (/cover|intro|lead/.test(name)) return '封面、开场或新章节引入；使用短标题和一句核心信息'
  if (/section/.test(name)) return '章节过渡；只呈现章节名和简短提示'
  if (/quote/.test(name)) return '引用、核心观点或关键原文；正文必须简短'
  if (/credit|end|thanks/.test(name)) return '结束页、致谢或来源说明'
  if (/four|grid|cell|panel|item/.test(name)) return '四个并列要点、分类或评价维度'
  if (/two-cols|columns|compare/.test(name)) return '比较、左右对应关系、概念与案例或问题与结论'
  if (/side-title/.test(name)) return '侧边强调标题配合较完整的解释内容'
  if (/top-title/.test(name)) return '顶部标题配合正文、图表或分栏内容'
  if (/timeline/.test(name)) return '时间发展、阶段变化或历史过程'
  if (/step/.test(name)) return '流程、方法、实验步骤或操作顺序'
  if (/diagram/.test(name)) return '概念关系、结构图或因果链'
  if (/figure|image|showcase|full/.test(name)) return '大图、图表、案例截图或沉浸式视觉页面'
  if (/fact|statement|bigtype/.test(name)) return '单个关键数字、结论或需要强强调的观点'
  if (/index|contents/.test(name)) return '目录、议程或章节索引'
  if (slots.some((slot) => slot !== 'default')) return '使用主题提供的命名区域组织结构化内容'
  return '常规正文页；用于无法匹配更专门布局的内容'
}

function markdownPattern(slots) {
  // 给每个 layout 构造可直接进入 prompt 的最小写法示例。
  const named = slots.filter((slot) => slot !== 'default')
  if (!named.length) return '# {{title}}\n\n{{body}}'
  const rows = named.map((slot) => `::${slot}::\n{{${slot}}}`)
  if (slots.includes('default')) rows.push('{{default}}')
  return rows.join('\n\n')
}

async function directoryVueNames(directory) {
  try {
    return (await readdir(directory, { withFileTypes: true }))
      .filter((entry) => entry.isFile() && entry.name.endsWith('.vue'))
      .map((entry) => entry.name.slice(0, -4))
      .sort()
  } catch {
    return []
  }
}

async function buildCapabilities(themeSpec, nodeModules) {
  // manifest 带 schema_version；扫描逻辑变化后会自动重建旧缓存。
  const cacheFile = path.join(packageThemeDir(themeSpec), 'capabilities.json')
  try {
    const cached = JSON.parse(await readFile(cacheFile, 'utf8'))
    if (cached.schema_version === capabilitySchemaVersion && cached.theme_spec === themeSpec) return cached
  } catch {
    // Rebuild stale or missing capability manifests.
  }

  const themeDir = themePackageDir(nodeModules, themeSpec)
  const layoutsDir = path.join(themeDir, 'layouts')
  const layoutFiles = await readdir(layoutsDir, { withFileTypes: true }).catch(() => [])
  const layouts = []
  for (const entry of layoutFiles) {
    if (!entry.isFile() || !entry.name.endsWith('.vue')) continue
    const name = entry.name.slice(0, -4)
    const source = await readFile(path.join(layoutsDir, entry.name), 'utf8')
    const slots = extractSlots(source)
    layouts.push({
      name,
      slots,
      props: extractProps(source),
      usage: layoutUsage(name, slots),
      markdown_pattern: markdownPattern(slots),
      supports_images: /image|figure|showcase|full|background/.test(name),
      structural: slots.some((slot) => slot !== 'default') || /cover|intro|section|quote/.test(name),
    })
  }
  layouts.sort((left, right) => left.name.localeCompare(right.name))
  const manifest = {
    schema_version: capabilitySchemaVersion,
    theme_spec: themeSpec,
    package_name: themePackageName(themeSpec),
    layouts,
    components: await directoryVueNames(path.join(themeDir, 'components')),
  }
  await writeFile(cacheFile, JSON.stringify(manifest), 'utf8')
  return manifest
}

async function capabilities(payload) {
  // 确保包已缓存后返回布局、组件和样式能力清单。
  const themeSpec = validatedTheme(payload)
  const nodeModules = await ensureThemePackage(themeSpec)
  return buildCapabilities(themeSpec, nodeModules)
}

async function installTheme(target, themeSpec) {
  // 在临时目录安装，再原子 rename 到缓存，失败不会污染可用版本。
  await mkdir(target, { recursive: true })
  await mkdir(npmCacheRoot, { recursive: true })
  await execFileAsync(
    'npm',
    [
      'install',
      '--ignore-scripts',
      '--legacy-peer-deps',
      '--omit=dev',
      '--no-audit',
      '--no-fund',
      '--no-package-lock',
      '--no-save',
      themeSpec,
    ],
    {
      cwd: target,
      timeout: 120_000,
      maxBuffer: 4 * 1024 * 1024,
      env: {
        ...process.env,
        npm_config_cache: npmCacheRoot,
        npm_config_update_notifier: 'false',
      },
    },
  )
}

async function linkHostDependencies(target) {
  // 主题运行时复用镜像中的 Vue/Slidev 依赖，减少每个主题重复安装。
  const nodeModules = path.join(target, 'node_modules')
  await mkdir(nodeModules, { recursive: true })
  for (const packageName of [
    'vite',
    'vue',
    '@slidev/types',
    '@slidev/client',
    '@slidev/parser',
    '@iconify-json/la',
    '@iconify-json/logos',
    '@iconify-json/simple-icons',
  ]) {
    const packageParts = packageName.split('/')
    const source = path.join('/app/node_modules', ...packageParts)
    const destination = path.join(nodeModules, ...packageParts)
    try {
      await access(destination)
    } catch {
      await mkdir(path.dirname(destination), { recursive: true })
      await symlink(source, destination, 'dir')
    }
  }
}

async function cachedPackage(themeSpec) {
  // 校验完成标记后才认为缓存可用。
  const target = packageThemeDir(themeSpec)
  try {
    const marker = JSON.parse(await readFile(path.join(target, 'theme.json'), 'utf8'))
    const nodeModules = path.join(target, 'node_modules')
    await access(nodeModules)
    return marker.theme_spec === themeSpec ? nodeModules : null
  } catch {
    return null
  }
}

async function legacyProjectCache(themeSpec) {
  // 兼容旧版按项目缓存，把已有包提升到全局复用缓存。
  try {
    const entries = await readdir(themeRoot, { withFileTypes: true })
    for (const entry of entries) {
      if (!entry.isDirectory() || !/^[0-9a-f-]{36}$/i.test(entry.name)) continue
      const target = path.join(themeRoot, entry.name)
      try {
        const marker = JSON.parse(await readFile(path.join(target, 'theme.json'), 'utf8'))
        await access(path.join(target, 'node_modules'))
        if (marker.theme_spec === themeSpec) return target
      } catch {
        // Ignore incomplete legacy project caches.
      }
    }
  } catch {
    // The theme root may not exist on the first run.
  }
  return null
}

async function ensureThemePackage(themeSpec) {
  // installs Map 合并同一主题的并发下载；后续项目直接复用落盘包。
  const cached = await cachedPackage(themeSpec)
  if (cached) {
    await linkHostDependencies(path.dirname(cached))
    return cached
  }
  if (installs.has(themeSpec)) return installs.get(themeSpec)

  const installation = (async () => {
    const secondCheck = await cachedPackage(themeSpec)
    if (secondCheck) return secondCheck

    await mkdir(packageRoot, { recursive: true })
    const target = packageThemeDir(themeSpec)
    const temporary = path.join(packageRoot, `.install-${packageCacheKey(themeSpec)}-${randomUUID()}`)
    try {
      const legacy = await legacyProjectCache(themeSpec)
      if (legacy) {
        await cp(legacy, temporary, { recursive: true })
      } else {
        await installTheme(temporary, themeSpec)
      }
      await linkHostDependencies(temporary)
      await writeFile(
        path.join(temporary, 'theme.json'),
        JSON.stringify({ theme_spec: themeSpec, cache_key: packageCacheKey(themeSpec) }),
        'utf8',
      )
      await rm(target, { recursive: true, force: true })
      await rename(temporary, target)
      return path.join(target, 'node_modules')
    } finally {
      await rm(temporary, { recursive: true, force: true })
    }
  })()

  installs.set(themeSpec, installation)
  try {
    return await installation
  } finally {
    installs.delete(themeSpec)
  }
}

async function prepare(payload) {
  // 为项目创建指向全局包缓存的轻量绑定，并返回能力清单。
  const themeSpec = validatedTheme(payload)
  const target = projectThemeDir(payload.project_id)
  await ensureThemePackage(themeSpec)
  await rm(target, { recursive: true, force: true })
  await mkdir(target, { recursive: true })
  await writeFile(
    path.join(target, 'theme.json'),
    JSON.stringify({ theme_spec: themeSpec, cache_key: packageCacheKey(themeSpec) }),
    'utf8',
  )
}

async function render(payload) {
  // 在受控 job 目录调用 Slidev export，生成后端期待的 PPTX。
  const { job_id: jobId, project_id: projectId } = payload
  if (!/^[0-9a-f-]{36}$/i.test(jobId || '')) throw new Error('INVALID_JOB_ID')
  const themeSpec = validatedTheme(payload)
  projectThemeDir(projectId)

  const jobDir = path.resolve(renderRoot, jobId)
  if (!jobDir.startsWith(`${renderRoot}${path.sep}`)) throw new Error('INVALID_JOB_PATH')
  const slides = path.join(jobDir, 'slides.md')
  const output = path.join(jobDir, 'output.pptx')
  await access(slides)
  const nodeModules = await ensureThemePackage(themeSpec)
  try {
    await rm(path.join(jobDir, 'node_modules'), { recursive: true, force: true })
    await symlink(nodeModules, path.join(jobDir, 'node_modules'), 'dir')
    const exportArgs = [
      'export',
      slides,
      '--format',
      'pptx',
      '--output',
      output,
      '--timeout',
      '90000',
      '--wait-until',
      'networkidle',
      '--wait',
      '1000',
    ]
    const exportOptions = {
      cwd: jobDir,
      timeout: 150_000,
      maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env },
    }
    await execFileAsync(slidevBin, exportArgs, exportOptions)
    await access(output)
  } finally {
    await unlink(path.join(jobDir, 'node_modules')).catch(() => {})
  }
}

async function renderPreview(payload) {
  // 只渲染请求页的 PNG，供后端按制品版本缓存。
  const { job_id: jobId, project_id: projectId } = payload
  if (!/^[0-9a-f-]{36}$/i.test(jobId || '')) throw new Error('INVALID_JOB_ID')
  const slideOrder = Number(payload.slide_order)
  const selectedSlide = Number.isInteger(slideOrder) && slideOrder > 0 ? slideOrder : null
  const themeSpec = validatedTheme(payload)
  projectThemeDir(projectId)

  const jobDir = path.resolve(renderRoot, jobId)
  if (!jobDir.startsWith(`${renderRoot}${path.sep}`)) throw new Error('INVALID_JOB_PATH')
  const slides = path.join(jobDir, 'slides.md')
  const output = path.join(jobDir, 'preview')
  await access(slides)
  const nodeModules = await ensureThemePackage(themeSpec)
  try {
    await rm(path.join(jobDir, 'node_modules'), { recursive: true, force: true })
    await symlink(nodeModules, path.join(jobDir, 'node_modules'), 'dir')
    await rm(output, { recursive: true, force: true })
    await execFileAsync(
      slidevBin,
      [
        'export',
        slides,
        '--format',
        'png',
        '--output',
        output,
        '--timeout',
        '90000',
        '--wait-until',
        'networkidle',
        '--wait',
        '500',
        '--scale',
        '1',
        ...(selectedSlide ? ['--range', String(selectedSlide)] : []),
      ],
      {
        cwd: jobDir,
        timeout: 150_000,
        maxBuffer: 8 * 1024 * 1024,
        env: { ...process.env },
      },
    )
    await access(path.join(output, `${selectedSlide || 1}.png`))
  } finally {
    await unlink(path.join(jobDir, 'node_modules')).catch(() => {})
  }
}

createServer(async (request, response) => {
  if (request.method === 'GET' && request.url === '/health') {
    return json(response, 200, { status: 'ok', service: 'slidev-renderer' })
  }
  if (request.method === 'POST' && request.url === '/prepare') {
    try {
      await prepare(await readJson(request))
      return json(response, 200, { status: 'ready' })
    } catch (error) {
      process.stderr.write(`${error?.stack || error}\n`)
      return json(response, 500, { status: 'failed', error: String(error?.message || error) })
    }
  }
  if (request.method === 'POST' && request.url === '/capabilities') {
    try {
      return json(response, 200, await capabilities(await readJson(request)))
    } catch (error) {
      process.stderr.write(`${error?.stack || error}\\n`)
      return json(response, 500, { status: 'failed', error: String(error?.message || error) })
    }
  }
  if (request.method === 'POST' && request.url === '/preview') {
    try {
      await renderPreview(await readJson(request))
      return json(response, 200, { status: 'succeeded' })
    } catch (error) {
      process.stderr.write(`${error?.stack || error}\n`)
      if (error?.stdout) process.stderr.write(`Slidev stdout:\n${error.stdout}\n`)
      if (error?.stderr) process.stderr.write(`Slidev stderr:\n${error.stderr}\n`)
      return json(response, 500, { status: 'failed', error: String(error?.message || error) })
    }
  }
  if (request.method !== 'POST' || request.url !== '/render') {
    return json(response, 404, { error: 'NOT_FOUND' })
  }
  try {
    await render(await readJson(request))
    return json(response, 200, { status: 'succeeded' })
  } catch (error) {
    process.stderr.write(`${error?.stack || error}\n`)
    if (error?.stdout) process.stderr.write(`Slidev stdout:\n${error.stdout}\n`)
    if (error?.stderr) process.stderr.write(`Slidev stderr:\n${error.stderr}\n`)
    return json(response, 500, { status: 'failed', error: String(error?.message || error) })
  }
}).listen(3010, '0.0.0.0', () => {
  process.stdout.write('Slidev renderer listening on 3010\n')
})
