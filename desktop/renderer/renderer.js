const els = {
  targetApp: document.getElementById('targetApp'),
  maxSteps: document.getElementById('maxSteps'),
  guiPause: document.getElementById('guiPause'),
  windowWidth: document.getElementById('windowWidth'),
  windowHeight: document.getElementById('windowHeight'),
  hideDuringRun: document.getElementById('hideDuringRun'),
  dryRun: document.getElementById('dryRun'),
  refreshPermissionsBtn: document.getElementById('refreshPermissionsBtn'),
  promptAccessibilityBtn: document.getElementById('promptAccessibilityBtn'),
  openAccessibilityBtn: document.getElementById('openAccessibilityBtn'),
  openScreenBtn: document.getElementById('openScreenBtn'),
  permissionTarget: document.getElementById('permissionTarget'),
  accessibilityStatus: document.getElementById('accessibilityStatus'),
  screenStatus: document.getElementById('screenStatus'),
  permissionHint: document.getElementById('permissionHint'),
  prompt: document.getElementById('prompt'),
  focusBtn: document.getElementById('focusBtn'),
  resizeBtn: document.getElementById('resizeBtn'),
  runBtn: document.getElementById('runBtn'),
  openTraceBtn: document.getElementById('openTraceBtn'),
  windowInfo: document.getElementById('windowInfo'),
  traceInfo: document.getElementById('traceInfo'),
  resultInfo: document.getElementById('resultInfo'),
  statusPill: document.getElementById('statusPill'),
  logView: document.getElementById('logView'),
  runOverlay: document.getElementById('runOverlay'),
  overlayTitle: document.getElementById('overlayTitle'),
  overlayCounter: document.getElementById('overlayCounter'),
  overlayPrompt: document.getElementById('overlayPrompt'),
  overlayStage: document.getElementById('overlayStage'),
  overlayStatus: document.getElementById('overlayStatus'),
  overlayDetail: document.getElementById('overlayDetail'),
  todoList: document.getElementById('todoList')
}

let lastTraceDir = ''
let permissionState = null
let currentTodoState = null

bootstrap()

async function bootstrap() {
  const defaults = await window.desktopApi.getDefaults()
  els.targetApp.value = defaults.targetApp
  els.prompt.value = defaults.prompt
  els.maxSteps.value = defaults.guiMaxSteps
  els.guiPause.value = defaults.guiPause
  els.windowWidth.value = defaults.width
  els.windowHeight.value = defaults.height
  els.hideDuringRun.checked = defaults.hideDuringRun
  els.dryRun.checked = false

  await refreshPermissions()
  await refreshWindowInfo()
  resetRunHud()

  window.desktopApi.onRunLog(({ text }) => {
    els.logView.textContent += text
    els.logView.scrollTop = els.logView.scrollHeight
  })

  window.desktopApi.onRunProgress(progress => {
    applyRunProgress(progress)
  })

  els.refreshPermissionsBtn.addEventListener('click', refreshPermissions)
  els.promptAccessibilityBtn.addEventListener('click', requestAccessibilityPrompt)
  els.openAccessibilityBtn.addEventListener('click', async () => {
    await openSettingsPane('accessibility')
  })
  els.openScreenBtn.addEventListener('click', async () => {
    await openSettingsPane('screen')
  })

  els.focusBtn.addEventListener('click', async () => {
    const response = await window.desktopApi.focusTarget({ appName: els.targetApp.value.trim() })
    applyPermissionResponse(response)
    if (!response.ok) {
      showActionError(response.error, 'Unable to focus the target app.')
      return
    }
    setWindowInfo(response.window)
  })

  els.resizeBtn.addEventListener('click', async () => {
    const response = await window.desktopApi.resizeTarget({
      appName: els.targetApp.value.trim(),
      width: Number(els.windowWidth.value),
      height: Number(els.windowHeight.value)
    })
    applyPermissionResponse(response)
    if (!response.ok) {
      showActionError(response.error, 'Unable to resize the target window.')
      return
    }
    setWindowInfo(response.window)
  })

  els.runBtn.addEventListener('click', runPrompt)
  els.openTraceBtn.addEventListener('click', async () => {
    if (!lastTraceDir) return
    await window.desktopApi.openTrace({ traceDir: lastTraceDir })
  })
}

async function refreshPermissions() {
  const response = await window.desktopApi.checkPermissions()
  applyPermissionResponse(response)
  if (!response.ok) {
    els.permissionHint.textContent = formatError(response.error)
  }
}

async function requestAccessibilityPrompt() {
  const response = await window.desktopApi.requestAccessibility()
  applyPermissionResponse(response)
  if (!response.ok) {
    showActionError(response.error, 'Unable to prompt for Accessibility access.')
    return
  }

  els.resultInfo.textContent = response.prompted
    ? 'macOS prompt requested. Enable access, then refresh status.'
    : 'Accessibility is already granted.'
}

async function openSettingsPane(pane) {
  const response = await window.desktopApi.openSystemSettings({ pane })
  if (!response.ok) {
    showActionError(response.error, 'Unable to open macOS System Settings.')
    return
  }

  els.resultInfo.textContent = `Opened macOS ${pane === 'screen' ? 'Screen Recording' : 'Accessibility'} settings.`
}

async function refreshWindowInfo() {
  const response = await window.desktopApi.getWindowInfo({ appName: els.targetApp.value.trim() })
  applyPermissionResponse(response)
  if (!response.ok) {
    els.windowInfo.textContent = formatError(response.error)
    return
  }
  setWindowInfo(response.window)
}

function setWindowInfo(info) {
  els.windowInfo.textContent = `${info.width}×${info.height} @ (${info.x}, ${info.y})`
  els.windowWidth.value = info.width
  els.windowHeight.value = info.height
}

async function runPrompt() {
  const windowResponse = await window.desktopApi.getWindowInfo({ appName: els.targetApp.value.trim() })
  applyPermissionResponse(windowResponse)
  if (windowResponse.ok) {
    setWindowInfo(windowResponse.window)
  }

  const prompt = els.prompt.value.trim()
  const payload = {
    appName: els.targetApp.value.trim(),
    prompt,
    maxSteps: Number(els.maxSteps.value),
    pause: Number(els.guiPause.value),
    dryRun: els.dryRun.checked,
    width: Number(els.windowWidth.value),
    height: Number(els.windowHeight.value),
    hideDuringRun: els.hideDuringRun.checked
  }

  beginRunHud(prompt)
  setRunning(true)
  els.logView.textContent = ''
  els.traceInfo.textContent = 'Running…'
  els.resultInfo.textContent = 'Executing GUI workflow'
  lastTraceDir = ''
  els.openTraceBtn.disabled = true

  const response = await window.desktopApi.runPrompt(payload)
  applyPermissionResponse(response)
  if (!response.ok) {
    finishRunHud({
      success: false,
      final_status: 'error',
      final_reason: formatError(response.error) || 'Run failed'
    })
    setRunning(false, false)
    els.resultInfo.textContent = formatError(response.error) || 'Run failed'
    els.traceInfo.textContent = 'No trace'
    if (response.stdout) els.logView.textContent += `\n${response.stdout}`
    if (response.stderr) els.logView.textContent += `\n${response.stderr}`
    if (response.error?.raw) els.logView.textContent += `\n${response.error.raw}`
    return
  }

  const result = response.result
  lastTraceDir = result.trace_dir
  els.traceInfo.textContent = result.trace_dir
  els.resultInfo.textContent = `${result.final_status} · ${result.final_reason}`
  els.openTraceBtn.disabled = false
  finishRunHud(result)
  setRunning(false, !!result.success)
}

function applyPermissionResponse(response) {
  if (!response || !response.permissions) return
  permissionState = response.permissions
  renderPermissionState(permissionState)
}

function renderPermissionState(state) {
  const targetLine = state.permissionTargetLabel === state.appName
    ? `${state.permissionTargetLabel} needs the permissions below.`
    : `${state.permissionTargetLabel} needs the permissions below. App name: ${state.appName}.`
  els.permissionTarget.textContent = `${targetLine} Current executable: ${state.execPath}`

  setPermissionBadge(
    els.accessibilityStatus,
    state.accessibilityGranted ? 'Granted' : 'Missing',
    state.accessibilityGranted ? 'ok' : 'error'
  )

  setPermissionBadge(
    els.screenStatus,
    screenDisplayLabel(state),
    state.screenGranted ? 'ok' : 'warn'
  )

  if (state.screenGranted && state.screenSource === 'capture' && state.screenReportedStatus !== 'granted') {
    els.permissionHint.textContent = 'Actual screencapture preflight passed. Electron reported a stale screen-permission status, but the GUI run should work.'
    return
  }

  if (state.accessibilityGranted && state.screenGranted) {
    els.permissionHint.textContent = 'Permissions look good. You can focus Feishu and run the GUI prompt.'
    return
  }

  if (!state.accessibilityGranted && !state.screenGranted) {
    els.permissionHint.textContent = `Grant Accessibility and Screen Recording to ${state.permissionTargetLabel}. After enabling Screen Recording, restart the desktop app once.`
    return
  }

  if (!state.accessibilityGranted) {
    els.permissionHint.textContent = `Grant Accessibility to ${state.permissionTargetLabel}, then retry focus or run.`
    return
  }

  els.permissionHint.textContent = `Grant Screen Recording to ${state.permissionTargetLabel}. After enabling it, restart the desktop app once before the next GUI run.`
}

function setPermissionBadge(element, text, tone) {
  element.textContent = text
  element.className = `permission-status ${tone}`
}

function screenStatusLabel(status) {
  const labels = {
    granted: 'Granted',
    denied: 'Denied',
    restricted: 'Restricted',
    'not-determined': 'Not Granted',
    unknown: 'Unknown'
  }
  return labels[status] || String(status || 'Unknown')
}

function screenDisplayLabel(state) {
  if (state.screenGranted && state.screenSource === 'capture' && state.screenReportedStatus !== 'granted') {
    return 'Granted via Capture'
  }
  return state.screenGranted ? 'Granted' : screenStatusLabel(state.screenStatus)
}

function showActionError(error, fallback) {
  const message = formatError(error) || fallback
  els.resultInfo.textContent = message
  if (error?.raw) {
    els.logView.textContent += `${els.logView.textContent ? '\n' : ''}${error.raw}\n`
  }
}

function formatError(error) {
  if (!error) return ''
  if (typeof error === 'string') return error
  return error.message || error.raw || JSON.stringify(error)
}

function setRunning(running, success = null) {
  els.runBtn.disabled = running
  els.focusBtn.disabled = running
  els.resizeBtn.disabled = running

  if (running) {
    els.statusPill.textContent = 'Running'
    els.statusPill.className = 'pill running'
    document.body.classList.add('run-active')
    return
  }

  document.body.classList.remove('run-active')

  if (success === true) {
    els.statusPill.textContent = 'Success'
    els.statusPill.className = 'pill success'
    return
  }

  if (success === false) {
    els.statusPill.textContent = 'Error'
    els.statusPill.className = 'pill error'
    return
  }

  els.statusPill.textContent = 'Idle'
  els.statusPill.className = 'pill idle'
}

function beginRunHud(prompt) {
  currentTodoState = {
    prompt,
    goalKind: detectGoalKind(prompt),
    targetMessage: extractTargetMessage(prompt),
    items: buildBootstrapTodoItems(prompt),
    status: 'Running',
    detail: 'Preparing the first visual observation.',
    stage: 'observe'
  }
  els.overlayTitle.textContent = overlayTitleForGoal(currentTodoState.goalKind)
  els.overlayPrompt.textContent = summarizePrompt(prompt) || 'Running GUI workflow.'
  els.overlayStatus.textContent = currentTodoState.status
  els.overlayStage.textContent = currentTodoState.stage
  els.overlayDetail.textContent = currentTodoState.detail
  renderTodoList(currentTodoState.items)
  updateOverlayCounter()
}

function resetRunHud() {
  currentTodoState = null
  els.overlayTitle.textContent = 'Awaiting run'
  els.overlayPrompt.textContent = 'Start a task to see the live checklist and verification state.'
  els.overlayStatus.textContent = 'waiting'
  els.overlayStage.textContent = 'idle'
  els.overlayDetail.textContent = 'The desktop shell will switch into a compact run HUD while the task is executing.'
  els.todoList.innerHTML = ''
  els.overlayCounter.textContent = '0/0'
}

function finishRunHud(result) {
  if (!currentTodoState) {
    resetRunHud()
    return
  }
  const tone = result.success ? 'done' : 'blocked'
  currentTodoState.status = result.success ? 'Success' : 'Blocked'
  currentTodoState.detail = result.final_reason || 'Run finished.'
  currentTodoState.stage = result.final_status || currentTodoState.stage
  if (result.success) {
    currentTodoState.items.forEach(item => {
      item.status = 'done'
    })
  } else {
    const active = currentTodoState.items.find(item => item.status === 'active')
    if (active) {
      active.status = tone
    }
  }
  els.overlayStatus.textContent = currentTodoState.status
  els.overlayStage.textContent = currentTodoState.stage
  els.overlayDetail.textContent = currentTodoState.detail
  renderTodoList(currentTodoState.items)
  updateOverlayCounter()
}

function applyRunProgress(progress) {
  if (!currentTodoState) {
    beginRunHud(els.prompt.value.trim())
  }

  if (progress.trace_dir) {
    lastTraceDir = progress.trace_dir
  }
  if (progress.goal_kind) {
    currentTodoState.goalKind = progress.goal_kind
    els.overlayTitle.textContent = overlayTitleForGoal(currentTodoState.goalKind)
  }
  if (progress.target_message) {
    currentTodoState.targetMessage = progress.target_message
  }

  currentTodoState.stage = progress.current_stage || progress.planner_stage || progress.perception_stage || 'observe'
  currentTodoState.status = progress.success === true
    ? 'Success'
    : progress.success === false
      ? 'Blocked'
      : progress.decision_status || 'Running'
  currentTodoState.detail = progress.message || progress.done_gate_reason || 'Running GUI workflow.'
  if (Array.isArray(progress.workflow_steps) && progress.workflow_steps.length) {
    currentTodoState.items = progress.workflow_steps.map(normalizeTodoItem)
  }

  els.overlayStatus.textContent = currentTodoState.status
  els.overlayStage.textContent = currentTodoState.stage
  els.overlayDetail.textContent = currentTodoState.detail
  renderTodoList(currentTodoState.items)
  updateOverlayCounter()
}

function renderTodoList(items) {
  els.todoList.innerHTML = ''
  for (const item of items) {
    const li = document.createElement('li')
    li.className = `todo-item ${item.status}`

    const row = document.createElement('div')
    row.className = 'todo-item-row'

    const title = document.createElement('span')
    title.className = 'todo-item-title'
    title.textContent = item.title

    const state = document.createElement('span')
    state.className = `todo-item-state ${item.status}`
    state.textContent = statusLabel(item.status)

    row.append(title, state)
    li.append(row)

    if (item.note) {
      const note = document.createElement('span')
      note.className = 'todo-item-copy'
      note.textContent = item.note
      li.appendChild(note)
    }
    els.todoList.appendChild(li)
  }
}

function updateOverlayCounter() {
  if (!currentTodoState) {
    els.overlayCounter.textContent = '0/0'
    return
  }
  const doneCount = currentTodoState.items.filter(item => item.status === 'done').length
  els.overlayCounter.textContent = `${doneCount}/${currentTodoState.items.length}`
}

function buildBootstrapTodoItems(prompt) {
  return [
    normalizeTodoItem({
      title: bootstrapTitleForGoal(detectGoalKind(prompt)),
      status: 'active'
    })
  ]
}

function normalizeTodoItem(item) {
  return {
    title: String(item?.title || 'Current step').trim() || 'Current step',
    status: normalizeTodoStatus(item?.status),
    note: String(item?.note || '').trim()
  }
}

function normalizeTodoStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  return ['pending', 'active', 'done', 'blocked'].includes(normalized) ? normalized : 'pending'
}

function statusLabel(status) {
  const labels = {
    pending: 'queued',
    active: 'live',
    done: 'done',
    blocked: 'blocked'
  }
  return labels[status] || 'queued'
}

function summarizePrompt(prompt) {
  const text = String(prompt || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > 96 ? `${text.slice(0, 96)}…` : text
}

function detectGoalKind(prompt) {
  const text = String(prompt || '').toLowerCase()
  const isCalendar = text.includes('calendar') || text.includes('日历') || text.includes('日程')
  if (isCalendar && (
    text.includes('create event') ||
    text.includes('new event') ||
    text.includes('创建event') ||
    text.includes('创建 event') ||
    text.includes('创建日程') ||
    text.includes('新建日程') ||
    text.includes('时间节点') ||
    text.includes('time slot')
  )) {
    return 'create_calendar_event'
  }
  if (isCalendar && (
    text.includes('open') ||
    text.includes('打开') ||
    text.includes('进入') ||
    text.includes('切换')
  )) {
    return 'open_calendar'
  }
  if ((text.includes('send') || text.includes('发送') || text.includes('发出')) &&
      (text.includes('message') || text.includes('消息') || text.includes('聊天') || text.includes('群聊'))) {
    return 'send_message'
  }
  if ((text.includes('chat') || text.includes('群聊') || text.includes('聊天') || text.includes('conversation')) &&
      (text.includes('open') || text.includes('switch') || text.includes('click') || text.includes('打开') || text.includes('切换') || text.includes('点击'))) {
    return 'open_chat'
  }
  return 'generic'
}

function overlayTitleForGoal(goalKind) {
  if (goalKind === 'send_message') return 'Sending message'
  if (goalKind === 'open_chat') return 'Opening chat'
  if (goalKind === 'open_calendar') return 'Opening Calendar'
  if (goalKind === 'create_calendar_event') return 'Creating calendar event'
  return 'Running task'
}

function bootstrapTitleForGoal(goalKind) {
  if (goalKind === 'send_message') return 'Observe current chat'
  if (goalKind === 'open_chat') return 'Open target conversation'
  if (goalKind === 'open_calendar') return 'Open Calendar module'
  if (goalKind === 'create_calendar_event') return 'Open Calendar and create event'
  return 'Observe target window'
}

function extractTargetMessage(prompt) {
  const text = String(prompt || '')
  const patterns = [
    /[“"]([^”"]{1,200})[”"]/,
    /'([^']{1,200})'/,
    /发送消息[:： ]+([^\n；;，,。]+)/i,
    /send message[: ]+([^\n;,.]+)/i
  ]
  for (const pattern of patterns) {
    const match = text.match(pattern)
    if (match) {
      return match[1].trim()
    }
  }
  return ''
}
