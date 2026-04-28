const { app, BrowserWindow, ipcMain, screen, shell, systemPreferences } = require('electron')
const { execFile, spawn } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = __dirname === process.cwd() ? __dirname : path.resolve(__dirname, '..')
const DEFAULT_WINDOW = { width: 420, height: 760 }
const MACOS_SETTINGS_URLS = {
  accessibility: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
  screen: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'
}

let mainWindow = null
let activeChild = null
let permissionCache = { expiresAt: 0, value: null }
let runWindowState = null
const GUI_PROGRESS_PREFIX = '__GUI_PROGRESS__'

function createWindow() {
  const windowOptions = {
    width: DEFAULT_WINDOW.width,
    height: DEFAULT_WINDOW.height,
    minWidth: 380,
    minHeight: 700,
    backgroundColor: '#111111',
    title: 'Lark GUI Console',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  }

  if (process.platform === 'darwin') {
    windowOptions.titleBarStyle = 'hiddenInset'
  }

  mainWindow = new BrowserWindow(windowOptions)

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

ipcMain.handle('app:get-defaults', async () => {
  const targetApp = process.env.GUI_TARGET_APP || process.env.CUA_TARGET_APP || 'Feishu'
  let detectedWindow = null
  try {
    detectedWindow = await getWindowInfo(targetApp)
  } catch {
    detectedWindow = null
  }
  return {
    targetApp,
    prompt: '当前打开的是飞书群聊 bot功能测试。请在当前聊天窗口发送消息 hello-world；如果输入框未聚焦，先聚焦；消息发送成功后结束。',
    guiMaxSteps: process.env.GUI_MAX_STEPS || process.env.CUA_MAX_STEPS || '10',
    guiPause: process.env.GUI_ACTION_PAUSE || process.env.CUA_ACTION_PAUSE || '0.5',
    width: detectedWindow ? String(detectedWindow.width) : '',
    height: detectedWindow ? String(detectedWindow.height) : '',
    hideDuringRun: true
  }
})

ipcMain.handle('app:focus-target', async (_, { appName }) => {
  try {
    const resolvedAppName = requireAppName(appName)
    await activateTargetWindow(resolvedAppName)
    return { ok: true, window: await getWindowInfo(resolvedAppName), permissions: await getPermissionState() }
  } catch (error) {
    return { ok: false, error: normalizeError(error), permissions: await getPermissionState() }
  }
})

ipcMain.handle('app:resize-target', async (_, { appName, width, height }) => {
  try {
    const resolvedAppName = requireAppName(appName)
    await resizeTargetWindow(resolvedAppName, Number(width), Number(height))
    return { ok: true, window: await getWindowInfo(resolvedAppName), permissions: await getPermissionState() }
  } catch (error) {
    return { ok: false, error: normalizeError(error), permissions: await getPermissionState() }
  }
})

ipcMain.handle('app:get-window-info', async (_, { appName }) => {
  try {
    const resolvedAppName = requireAppName(appName)
    return { ok: true, window: await getWindowInfo(resolvedAppName), permissions: await getPermissionState() }
  } catch (error) {
    return { ok: false, error: normalizeError(error), permissions: await getPermissionState() }
  }
})

ipcMain.handle('app:check-permissions', async () => {
  return { ok: true, permissions: await getPermissionState({ forceRefresh: true }) }
})

ipcMain.handle('app:request-accessibility', async () => {
  if (process.platform !== 'darwin') {
    return {
      ok: true,
      prompted: false,
      permissions: await getPermissionState({ forceRefresh: true })
    }
  }

  try {
    const trusted = systemPreferences.isTrustedAccessibilityClient(true)
    return { ok: true, prompted: !trusted, permissions: await getPermissionState({ forceRefresh: true }) }
  } catch (error) {
    return { ok: false, error: normalizeError(error), permissions: await getPermissionState({ forceRefresh: true }) }
  }
})

ipcMain.handle('app:open-system-settings', async (_, { pane }) => {
  if (process.platform === 'win32') {
    const windowsUrl =
      pane === 'screen'
        ? 'ms-settings:privacy-broadfilesystemaccess'
        : 'ms-settings:easeofaccess-display'
    try {
      await shell.openExternal(windowsUrl)
      return { ok: true, pane, url: windowsUrl }
    } catch (error) {
      return { ok: false, error: normalizeError(error) }
    }
  }

  const url = MACOS_SETTINGS_URLS[pane]
  if (!url) {
    return {
      ok: false,
      error: normalizeError(createError('UNKNOWN_SETTINGS_PANE', `Unknown settings pane: ${pane}`))
    }
  }

  try {
    await shell.openExternal(url)
    return { ok: true, pane, url }
  } catch (error) {
    return { ok: false, error: normalizeError(error) }
  }
})

ipcMain.handle('app:open-trace', async (_, { traceDir }) => {
  if (!traceDir) {
    return {
      ok: false,
      error: normalizeError(createError('MISSING_TRACE_DIR', 'Missing traceDir.'))
    }
  }
  const result = await shell.openPath(traceDir)
  return { ok: result === '', error: result || null }
})

ipcMain.handle('app:run-prompt', async (_, payload) => {
  if (activeChild) {
    return {
      ok: false,
      error: normalizeError(createError('RUN_ALREADY_IN_PROGRESS', 'A run is already in progress.')),
      permissions: await getPermissionState()
    }
  }

  const {
    appName,
    prompt,
    maxSteps,
    pause,
    dryRun,
    width,
    height,
    hideDuringRun
  } = payload

  const resolvedAppName = String(appName || '').trim()
  if (!prompt || !prompt.trim()) {
    return {
      ok: false,
      error: normalizeError(createError('EMPTY_PROMPT', 'Prompt is empty.')),
      permissions: await getPermissionState()
    }
  }

  if (!resolvedAppName) {
    return {
      ok: false,
      error: normalizeError(createError('MISSING_TARGET_APP', 'Target app is empty.')),
      permissions: await getPermissionState()
    }
  }

  const permissions = await getPermissionState({ forceRefresh: true })
  if (!permissions.accessibilityGranted) {
    return {
      ok: false,
      error: normalizeError(
        createError(
          'ACCESSIBILITY_DENIED',
          `Grant Accessibility access to ${permissions.permissionTargetLabel} before focusing or controlling ${resolvedAppName}.`
        )
      ),
      permissions
    }
  }

  if (!permissions.screenGranted) {
    return {
      ok: false,
      error: normalizeError(
        createError(
          'SCREEN_RECORDING_DENIED',
          `Grant Screen Recording to ${permissions.permissionTargetLabel} before running the visual GUI loop.`
        )
      ),
      permissions
    }
  }

  const compactDuringRun = Boolean(hideDuringRun)

  try {
    await activateTargetWindow(resolvedAppName)
    if (width && height) {
      await resizeTargetWindow(resolvedAppName, Number(width), Number(height))
    }
    if (compactDuringRun && mainWindow) {
      enterRunHudMode()
      await activateTargetWindow(resolvedAppName)
    }

    const result = await runGuiPrompt({
      appName: resolvedAppName,
      prompt,
      maxSteps,
      pause,
      dryRun
    })

    if (mainWindow) {
      exitRunHudMode()
      mainWindow.show()
      mainWindow.focus()
    }

    return {
      ...result,
      permissions: await getPermissionState({ forceRefresh: true })
    }
  } catch (error) {
    if (mainWindow) {
      exitRunHudMode()
      mainWindow.show()
      mainWindow.focus()
    }
    return { ok: false, error: normalizeError(error), permissions: await getPermissionState({ forceRefresh: true }) }
  }
})

function runGuiPrompt({ appName, prompt, maxSteps, pause, dryRun }) {
  return new Promise((resolve, reject) => {
    const args = [
      'run',
      '--locked',
      'python',
      'run.py',
      'gui-run',
      prompt,
      '--json-output'
    ]

    if (maxSteps) {
      args.push('--max-steps', String(maxSteps))
    }
    if (pause) {
      args.push('--pause', String(pause))
    }
    if (dryRun) {
      args.push('--dry-run')
    }

    const child = spawn('uv', args, {
      cwd: ROOT,
      env: {
        ...process.env,
        GUI_TARGET_APP: appName,
        GUI_PROGRESS_STDERR: '1'
      }
    })
    activeChild = child

    let stdout = ''
    let stderr = ''
    let stdoutBuffer = ''
    let stderrBuffer = ''

    child.stdout.on('data', chunk => {
      const text = chunk.toString()
      stdout += text
      stdoutBuffer += text
      stdoutBuffer = consumeStreamBuffer(stdoutBuffer, 'stdout')
    })

    child.stderr.on('data', chunk => {
      const text = chunk.toString()
      stderr += text
      stderrBuffer += text
      stderrBuffer = consumeStreamBuffer(stderrBuffer, 'stderr')
    })

    child.on('error', error => {
      activeChild = null
      reject(error)
    })

    child.on('close', code => {
      activeChild = null
      if (stdoutBuffer) {
        sendLog(stdoutBuffer, 'stdout')
      }
      if (stderrBuffer) {
        sendLog(stderrBuffer, 'stderr')
      }
      const parsed = parseJsonOutput(stdout)
      if (code === 0 && parsed) {
        resolve({
          ok: true,
          result: parsed,
          stdout,
          stderr
        })
        return
      }
      resolve({
        ok: false,
        code,
        stdout,
        stderr,
        error: parsed?.final_reason || stderr || stdout || `Process exited with ${code}`
      })
    })
  })
}

function sendLog(text, channel) {
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents.send('run:log', { text, channel })
}

function sendProgress(progress) {
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents.send('run:progress', progress)
}

function consumeStreamBuffer(buffer, channel) {
  const lines = buffer.split(/\r?\n/)
  const remainder = lines.pop() || ''
  for (const line of lines) {
    if (!line) {
      sendLog('\n', channel)
      continue
    }
    if (channel === 'stderr' && line.startsWith(GUI_PROGRESS_PREFIX)) {
      try {
        sendProgress(JSON.parse(line.slice(GUI_PROGRESS_PREFIX.length)))
      } catch {
        sendLog(`${line}\n`, channel)
      }
      continue
    }
    sendLog(`${line}\n`, channel)
  }
  return remainder
}

function enterRunHudMode() {
  if (!mainWindow || mainWindow.isDestroyed() || runWindowState) return
  runWindowState = {
    bounds: mainWindow.getBounds(),
    alwaysOnTop: mainWindow.isAlwaysOnTop()
  }
  const display = screen.getDisplayMatching(mainWindow.getBounds())
  const workArea = display.workArea
  const width = 388
  const height = 320
  const margin = 20
  const x = workArea.x + workArea.width - width - margin
  const y = workArea.y + margin
  mainWindow.setAlwaysOnTop(true, 'floating')
  mainWindow.setBounds({ x, y, width, height }, true)
}

function exitRunHudMode() {
  if (!mainWindow || mainWindow.isDestroyed() || !runWindowState) return
  const previous = runWindowState
  runWindowState = null
  mainWindow.setAlwaysOnTop(previous.alwaysOnTop)
  mainWindow.setBounds(previous.bounds, true)
}

function parseJsonOutput(stdout) {
  const trimmed = stdout.trim()
  if (!trimmed) return null
  try {
    return JSON.parse(trimmed)
  } catch {
    return null
  }
}

function runAppleScript(script) {
  return new Promise((resolve, reject) => {
    execFile('osascript', ['-e', script], { cwd: ROOT }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || error.message))
        return
      }
      resolve(stdout.trim())
    })
  })
}

function runPowerShell(script) {
  return new Promise((resolve, reject) => {
    execFile('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { cwd: ROOT }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || stdout || error.message))
        return
      }
      resolve(stdout.trim())
    })
  })
}

function activateTargetWindow(appName) {
  if (process.platform === 'win32') {
    return runPowerShell(windowsWindowScript(appName, { action: 'activate' }))
  }
  return runAppleScript(`tell application "${escapeAppleScript(appName)}" to activate`)
}

function resizeTargetWindow(appName, width, height) {
  if (process.platform === 'win32') {
    return runPowerShell(windowsWindowScript(appName, { action: 'resize', width, height }))
  }
  return runAppleScript(
    `tell application "System Events" to tell application process "${escapeAppleScript(appName)}" to tell front window to set size to {${Number(width)}, ${Number(height)}}`
  )
}

async function getWindowInfo(appName) {
  if (process.platform === 'win32') {
    const output = await runPowerShell(windowsWindowScript(appName, { action: 'info' }))
    const data = JSON.parse(output)
    return {
      x: data.x,
      y: data.y,
      width: data.width,
      height: data.height
    }
  }
  const output = await runAppleScript(
    listWindowsScript(appName)
  )
  const windows = parseWindowList(output)
  if (!windows.length) {
    throw createError('WINDOW_INFO_PARSE_FAILED', `Unexpected window info output: ${output}`, output)
  }
  const parts = selectMainWindow(windows)
  return {
    x: parts[0],
    y: parts[1],
    width: parts[2],
    height: parts[3]
  }
}

function windowsWindowScript(appName, options) {
  const appLiteral = psSingleQuote(appName)
  const actionLiteral = psSingleQuote(options.action)
  const width = Number(options.width || 0)
  const height = Number(options.height || 0)
  return `
$ErrorActionPreference = 'Stop'
$appName = '${appLiteral}'
$action = '${actionLiteral}'
$targetWidth = ${width}
$targetHeight = ${height}
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Window {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}
public struct RECT {
  public int Left;
  public int Top;
  public int Right;
  public int Bottom;
}
"@
$candidates = @($appName)
if ($appName.ToLowerInvariant() -in @('feishu', 'lark')) {
  $candidates += @('飞书', 'Lark')
}
$processes = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle }
$window = $null
foreach ($candidate in $candidates) {
  $window = $processes | Where-Object { $_.MainWindowTitle -like "*$candidate*" } | Sort-Object @{ Expression = { $_.MainWindowTitle.Length } } | Select-Object -First 1
  if ($window) { break }
}
if (-not $window) {
  $preview = ($processes | Select-Object -First 10 -ExpandProperty MainWindowTitle) -join ', '
  throw "No usable window found for '$appName'. Open the target app first or set GUI_TARGET_APP to part of its window title. Visible windows: $preview"
}
$handle = $window.MainWindowHandle
[Win32Window]::ShowWindow($handle, 9) | Out-Null
if ($action -eq 'activate' -or $action -eq 'resize') {
  [Win32Window]::SetForegroundWindow($handle) | Out-Null
  Start-Sleep -Milliseconds 200
}
$rect = New-Object RECT
[Win32Window]::GetWindowRect($handle, [ref]$rect) | Out-Null
if ($action -eq 'resize' -and $targetWidth -gt 0 -and $targetHeight -gt 0) {
  [Win32Window]::MoveWindow($handle, $rect.Left, $rect.Top, $targetWidth, $targetHeight, $true) | Out-Null
  Start-Sleep -Milliseconds 200
  [Win32Window]::GetWindowRect($handle, [ref]$rect) | Out-Null
}
[pscustomobject]@{
  x = $rect.Left
  y = $rect.Top
  width = $rect.Right - $rect.Left
  height = $rect.Bottom - $rect.Top
  title = $window.MainWindowTitle
} | ConvertTo-Json -Compress
`.trim()
}

function psSingleQuote(value) {
  return String(value).replace(/'/g, "''")
}

async function getPermissionState({ forceRefresh = false } = {}) {
  if (!forceRefresh && permissionCache.value && permissionCache.expiresAt > Date.now()) {
    return permissionCache.value
  }

  const execPath = process.execPath
  const binaryName = path.basename(execPath)
  const appName = app.getName() || binaryName

  if (process.platform !== 'darwin') {
    const state = {
      platform: process.platform,
      appName,
      binaryName,
      execPath,
      permissionTargetLabel: appName,
      accessibilityGranted: true,
      screenStatus: 'granted',
      screenGranted: true,
      screenSource: 'platform',
      settingsUrls: { ...MACOS_SETTINGS_URLS }
    }
    permissionCache = { value: state, expiresAt: Date.now() + 1500 }
    return state
  }

  const accessibilityGranted = systemPreferences.isTrustedAccessibilityClient(false)
  const reportedScreenStatus = systemPreferences.getMediaAccessStatus('screen')
  const captureCheck = await checkScreenCapturePermission()
  const screenGranted = captureCheck.ok || reportedScreenStatus === 'granted'

  const state = {
    platform: process.platform,
    appName,
    binaryName,
    execPath,
    permissionTargetLabel: binaryName === 'Electron' ? 'Electron' : appName,
    accessibilityGranted,
    screenStatus: screenGranted ? 'granted' : reportedScreenStatus,
    screenGranted,
    screenSource: captureCheck.ok ? 'capture' : 'electron',
    screenReportedStatus: reportedScreenStatus,
    screenCaptureGranted: captureCheck.ok,
    screenCaptureBytes: captureCheck.bytes || 0,
    screenCaptureError: captureCheck.error || null,
    settingsUrls: { ...MACOS_SETTINGS_URLS }
  }
  permissionCache = { value: state, expiresAt: Date.now() + 1500 }
  return state
}

function requireAppName(appName) {
  const resolved = String(appName || '').trim()
  if (!resolved) {
    throw createError('MISSING_TARGET_APP', 'Target app is empty.')
  }
  return resolved
}

function createError(code, message, raw = null) {
  const error = new Error(message)
  error.code = code
  error.raw = raw || message
  return error
}

function normalizeError(error) {
  const raw = error?.raw || error?.message || String(error)
  const message = error?.message || raw
  const explicitCode = error?.code
  const lower = raw.toLowerCase()

  if (explicitCode) {
    return { code: explicitCode, message, raw }
  }

  if (lower.includes('assistive access') || lower.includes('(-1719)')) {
    return {
      code: 'ACCESSIBILITY_DENIED',
      message: 'macOS Accessibility access is missing for this desktop app.',
      raw
    }
  }

  if (lower.includes('screen recording') || lower.includes('screencapture')) {
    return {
      code: 'SCREEN_RECORDING_DENIED',
      message: 'macOS Screen Recording access is missing for this desktop app.',
      raw
    }
  }

  if (lower.includes('not authorized to send apple events') || lower.includes('(-1743)')) {
    return {
      code: 'APPLE_EVENTS_DENIED',
      message: 'macOS blocked Apple Events automation for this desktop app.',
      raw
    }
  }

  if (lower.includes("application isn't running") || lower.includes('application is not running') || lower.includes('(-600)')) {
    return {
      code: 'TARGET_APP_NOT_RUNNING',
      message: 'The target app is not running.',
      raw
    }
  }

  if (lower.includes("can't get front window") || lower.includes('can’t get front window') || lower.includes('(-1728)')) {
    return {
      code: 'TARGET_WINDOW_NOT_FOUND',
      message: 'The target app does not expose a front window right now.',
      raw
    }
  }

  return {
    code: 'UNKNOWN_ERROR',
    message,
    raw
  }
}

function escapeAppleScript(value) {
  return String(value).replace(/"/g, '\\"')
}

function listWindowsScript(appName) {
  return `
tell application "System Events"
  tell application process "${escapeAppleScript(appName)}"
    set outputText to ""
    repeat with w in every window
      try
        set {px, py} to position of w
        set {sw, sh} to size of w
        set outputText to outputText & (px as text) & "," & (py as text) & "," & (sw as text) & "," & (sh as text) & linefeed
      end try
    end repeat
    return outputText
  end tell
end tell`.trim()
}

function parseWindowList(output) {
  return String(output || '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(parseBounds)
    .filter(Boolean)
}

function parseBounds(line) {
  const parts = String(line)
    .split(',')
    .map(part => Number(part.trim()))
  if (parts.length !== 4 || parts.some(Number.isNaN)) {
    return null
  }
  return parts
}

function selectMainWindow(windows) {
  const valid = windows.filter(window => window[2] > 0 && window[3] > 0)
  if (!valid.length) {
    throw createError('WINDOW_INFO_PARSE_FAILED', `No valid windows: ${JSON.stringify(windows)}`)
  }
  return valid.sort((a, b) => {
    const areaDiff = b[2] * b[3] - a[2] * a[3]
    if (areaDiff !== 0) return areaDiff
    if (b[2] !== a[2]) return b[2] - a[2]
    if (b[3] !== a[3]) return b[3] - a[3]
    if (a[1] !== b[1]) return a[1] - b[1]
    return a[0] - b[0]
  })[0]
}

async function checkScreenCapturePermission() {
  if (process.platform !== 'darwin') {
    return { ok: true, bytes: 0, error: null }
  }

  let tempDir = null
  try {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'cua-screen-check-'))
    const screenshotPath = path.join(tempDir, 'permission-check.png')
    await runCommand('screencapture', ['-x', screenshotPath])
    const stats = fs.statSync(screenshotPath)
    const ok = stats.isFile() && stats.size > 0
    return {
      ok,
      bytes: ok ? stats.size : 0,
      error: ok ? null : 'screencapture produced an empty file'
    }
  } catch (error) {
    return {
      ok: false,
      bytes: 0,
      error: error?.message || String(error)
    }
  } finally {
    if (tempDir) {
      fs.rmSync(tempDir, { recursive: true, force: true })
    }
  }
}

function runCommand(command, args) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { cwd: ROOT }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || stdout || error.message))
        return
      }
      resolve({ stdout: stdout.trim(), stderr: stderr.trim() })
    })
  })
}
