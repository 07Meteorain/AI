// 最小复现：Windows 下所有子进程启动即失败（0xC0000142）
// 用法：node repro.js          （受限环境下会打印 3221225794）
const { spawnSync } = require('child_process');

const PROBES = [
  ['cmd.exe', ['/c', 'echo hi'], 'inherit'],
  ['git', ['--version'], 'inherit'],
  ['where', ['git'], 'inherit'],
  ['cmd.exe', ['/c', 'echo hi'], 'ignore'],
  ['cmd.exe', ['/c', 'echo hi'], 'file'],
];

function fsStdio() {
  const fs = require('fs');
  return ['ignore', fs.openSync('probe_stdout.txt', 'w'), fs.openSync('probe_stderr.txt', 'w')];
}

let fail = 0;
for (const [cmd, args, mode] of PROBES) {
  const stdio = mode === 'file' ? fsStdio() : mode;
  const r = spawnSync(cmd, args, { stdio });
  const status = r.status;
  const err = r.error ? r.error.code : '-';
  const hex = status ? '0x' + (status >>> 0).toString(16).toUpperCase() : '-';
  if (status !== 0) fail += 1;
  console.log(`${cmd.padEnd(8)} stdio=${mode.padEnd(7)} status=${String(status).padEnd(11)} ${hex.padEnd(10)} err=${err}`);
}

console.log(fail === 0 ? '\n全部通过：进程创建正常' : `\n${fail} 项失败：进程创建被环境拦截`);
process.exit(fail === 0 ? 0 : 1);