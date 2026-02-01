module.exports = {
  apps: [{
    name: 'seosoyoung',
    script: 'venv/Scripts/python.exe',
    args: 'scripts/wrapper.py',
    cwd: 'D:/soyoung_root/seosoyoung_runtime',
    interpreter: 'none',
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
