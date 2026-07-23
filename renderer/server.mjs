import { execFile } from 'node:child_process'
import { createServer } from 'node:http'
import { access, mkdir, readFile, rm, symlink, unlink, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const renderRoot = path.resolve(process.env.RENDER_ROOT || '/data/render_jobs')
const themeRoot = path.resolve(process.env.THEME_ROOT || '/data/themes')
const slidevBin = '/app/node_modules/.bin/slidev'
const allowedThemes = new Set([
  '@slidev/theme-default@0.25.0',
  '@slidev/theme-seriph@0.25.0',
  '@slidev/theme-apple-basic@0.25.1',
  '@slidev/theme-bricks@0.25.0',
  'slidev-theme-tahta@0.13.2',
])

function json(response, status, payload) {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
  response.end(JSON.stringify(payload))
}

async function readJson(request) {
  let body = ''
  for await (const chunk of request) {
    body += chunk
    if (body.length > 64 * 1024) throw new Error('REQUEST_TOO_LARGE')
  }
  return JSON.parse(body || '{}')
}

function validatedTheme(payload) {
  const themeSpec = `${payload.theme_package}@${payload.theme_version}`
  if (!allowedThemes.has(themeSpec)) throw new Error('THEME_NOT_ALLOWED')
  return themeSpec
}

function projectThemeDir(projectId) {
  if (!/^[0-9a-f-]{36}$/i.test(projectId || '')) throw new Error('INVALID_PROJECT_ID')
  const target = path.resolve(themeRoot, projectId)
  if (!target.startsWith(`${themeRoot}${path.sep}`)) throw new Error('INVALID_THEME_PATH')
  return target
}

async function installTheme(target, themeSpec) {
  await mkdir(target, { recursive: true })
  try {
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
          npm_config_cache: path.join(target, '.npm-cache'),
          npm_config_update_notifier: 'false',
        },
      },
    )
  } finally {
    await rm(path.join(target, '.npm-cache'), { recursive: true, force: true })
  }
}

async function prepare(payload) {
  const themeSpec = validatedTheme(payload)
  const target = projectThemeDir(payload.project_id)
  const markerPath = path.join(target, 'theme.json')
  try {
    const marker = JSON.parse(await readFile(markerPath, 'utf8'))
    await access(path.join(target, 'node_modules'))
    if (marker.theme_spec === themeSpec) return
  } catch {
    // Missing or stale caches are replaced below.
  }
  await rm(target, { recursive: true, force: true })
  await installTheme(target, themeSpec)
  await writeFile(markerPath, JSON.stringify({ theme_spec: themeSpec }), 'utf8')
}

async function cachedNodeModules(projectId, themeSpec) {
  if (!projectId) return null
  const target = projectThemeDir(projectId)
  try {
    const marker = JSON.parse(await readFile(path.join(target, 'theme.json'), 'utf8'))
    const nodeModules = path.join(target, 'node_modules')
    await access(nodeModules)
    return marker.theme_spec === themeSpec ? nodeModules : null
  } catch {
    return null
  }
}

async function render(payload) {
  const { job_id: jobId, project_id: projectId } = payload
  if (!/^[0-9a-f-]{36}$/i.test(jobId || '')) throw new Error('INVALID_JOB_ID')
  const themeSpec = validatedTheme(payload)

  const jobDir = path.resolve(renderRoot, jobId)
  if (!jobDir.startsWith(`${renderRoot}${path.sep}`)) throw new Error('INVALID_JOB_PATH')
  const slides = path.join(jobDir, 'slides.md')
  const output = path.join(jobDir, 'output.pptx')
  await access(slides)
  let linkedTheme = false
  try {
    const cached = await cachedNodeModules(projectId, themeSpec)
    if (cached) {
      await symlink(cached, path.join(jobDir, 'node_modules'), 'dir')
      linkedTheme = true
    } else {
      await installTheme(jobDir, themeSpec)
    }
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
    if (linkedTheme) {
      await unlink(path.join(jobDir, 'node_modules')).catch(() => {})
    } else {
      await rm(path.join(jobDir, 'node_modules'), { recursive: true, force: true })
    }
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
