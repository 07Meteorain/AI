# 【求助】Windows 下所有子进程启动即失败 0xC0000142，且换 stdio 后错误变成 EPERM

## 一、环境
- Windows 11 24H2，单机单用户，两个终端都能复现
- Node 22 / Python 3.14.2 / Git 2.55，三者表现一致
- 同一份脚本在 CI（Linux）上完全正常，只有本机装了一款"终端安全/DLP"客户端

## 二、我在做什么（目标）
想用 Node 的 `child_process` 批量调 `git`，做一个提交前自动检查脚本；
**期望**它在本地也像 CI 一样跑通。

## 三、现象
调用任何子进程都直接返回退出码 **3221225794**（= `0xC0000142`，STATUS_DLL_INIT_FAILED），
stdout / stderr 全空，0.1 秒内返回，看不出"执行了一半"的痕迹。

## 四、已尝试（每条都带结果）
1. `stdio: "inherit"` → 仍然 3221225794
2. `stdio: "ignore"` → 仍然 3221225794
3. 把命令换成 `cmd.exe` 绝对路径 → 仍然 3221225794（说明不是 PATH 问题）
4. `stdio: "pipe"` → 错误变成 **EPERM**，不再是 0xC0000142（这一步把我卡住了）
5. 在"以管理员身份运行"的终端里跑同一条命令 → status=0，git 正常打印版本

## 五、证据
触发点在 `repro.js` 第 3 行的 `spawnSync` 调用。最小复现：

```js
const { spawnSync } = require('child_process');
for (const c of ['cmd.exe', 'git', 'where']) {
  const r = spawnSync(c, ['--version'], { stdio: 'inherit' });
  console.log(c, 'status=', r.status, 'err=', r.error && r.error.code);
}
```

实测输出（节选）：

```text
cmd.exe status= 3221225794
git     status= 3221225794
where   status= 3221225794
```

## 六、期望 vs 实际
- **期望**：三个探针都打印版本号，脚本继续往下走。
- **实际**：三个全部 0xC0000142；唯一变化是 pipe 模式变成 EPERM。

## 七、想问的具体问题
1. STATUS_DLL_INIT_FAILED 出现在**子进程启动阶段**，除了"安全软件注入 / 缺 VC 运行库"，还有哪类原因会让**连 cmd.exe 都挂**？我该用哪个工具（Procmon？）在三分钟内定位到是哪个 DLL？
2. 为什么 `stdio: "pipe"` 会变成 EPERM 而不是同一个 0xC0000142？这两条路径在 Windows 上的差异，是我理解错了，还是有更底层的原因？
