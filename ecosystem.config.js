module.exports = {
  apps: [{
    name: 'seosoyoung',
    script: 'scripts/start.ps1',
    cwd: 'D:/soyoung_root/seosoyoung_runtime',
    interpreter: 'powershell',
    interpreter_args: '-ExecutionPolicy Bypass -File',
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    error_file: 'logs/pm2-error.log',
    out_file: 'logs/pm2-out.log',
    merge_logs: true,
    autorestart: false,  // wrapper가 재시작 로직을 관리
    watch: false,
    env: {
      PYTHONUTF8: '1',
      PYTHONPATH: 'D:/soyoung_root/seosoyoung_runtime/src'
    }
  }]
};
