const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopApi', {
  getDefaults: () => ipcRenderer.invoke('app:get-defaults'),
  focusTarget: payload => ipcRenderer.invoke('app:focus-target', payload),
  resizeTarget: payload => ipcRenderer.invoke('app:resize-target', payload),
  getWindowInfo: payload => ipcRenderer.invoke('app:get-window-info', payload),
  checkPermissions: () => ipcRenderer.invoke('app:check-permissions'),
  requestAccessibility: () => ipcRenderer.invoke('app:request-accessibility'),
  openSystemSettings: payload => ipcRenderer.invoke('app:open-system-settings', payload),
  runPrompt: payload => ipcRenderer.invoke('app:run-prompt', payload),
  openTrace: payload => ipcRenderer.invoke('app:open-trace', payload),
  onRunLog: handler => {
    const wrapped = (_, data) => handler(data)
    ipcRenderer.on('run:log', wrapped)
    return () => ipcRenderer.removeListener('run:log', wrapped)
  },
  onRunProgress: handler => {
    const wrapped = (_, data) => handler(data)
    ipcRenderer.on('run:progress', wrapped)
    return () => ipcRenderer.removeListener('run:progress', wrapped)
  }
})
