const { spawn } = require('node:child_process')
const path = require('node:path')

delete process.env.ELECTRON_RUN_AS_NODE

const electronBinary = require('electron')

const child = spawn(electronBinary, ['.'], {
  cwd: path.join(__dirname, '..'),
  stdio: 'inherit',
  shell: false,
  env: process.env,
})

child.on('exit', code => {
  process.exit(code ?? 0)
})

child.on('error', error => {
  console.error('[desktop] Failed to launch Electron:', error.message)
  process.exit(1)
})
