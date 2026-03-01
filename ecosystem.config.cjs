module.exports = {
  apps: [
    {
      name: 'scheduler-api',
      cwd: './backend',
      script: 'main.py',
      interpreter: 'python',
      watch: false,
      autorestart: true,
      max_restarts: 50,
      min_uptime: '10s',
      restart_delay: 3000,
      env: {
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      name: 'scheduler-frontend',
      cwd: './frontend',
      script: 'node_modules/.bin/vite',
      args: '--port 5173 --host',
      watch: false,
      autorestart: true,
      max_restarts: 20,
      min_uptime: '5s',
      restart_delay: 2000,
    },
  ],
}
