# ohos-remote 规划

## 目标
PC（先 Windows）远程查看并控制 OpenHarmony 设备；不依赖系统签名、不做设备端 App。

## 里程碑
- **M0（完成）**：hdc 封装、设备列表、模型读取。
- **M1（完成）**：截图循环 + Tkinter 显示 + FPS/延迟状态。
- **M2（完成）**：点击/拖拽/文本注入（点击拖拽改 uinput，文本仍 uitest）；返回键已验证。
- **M3（完成）**：文件 push/pull、应用安装、shell、日志面板；PyInstaller 打包 `dist/ohos-remote.exe`（约 30MB，已实测）。
- **M4（基本完成）**：无线 tconn、PyInstaller 打包；多设备仅列表切换。

## 架构
```
src/hdc.py    hdc 子进程封装（serialize、超时、错误）
src/mirror.py 后台截图线程 → queue（丢旧帧）
src/app.py    Tkinter UI、坐标映射、输入事件
```
截图路径：`snapshot_display -f /data/local/tmp/ohosremote_*.jpeg` → `hdc file recv` → Pillow 解码。

## 已知限制与延迟归因（2026-11-18 实测）
- **抓图是硬瓶颈**：设备端 `snapshot_display` 单帧 400~450ms；即使 `-w 540 -h 1204` 也不下降；经 hdc 约 500~550ms（hdc 往返本身约 80ms）。因此循环上限约 2~2.5fps。
- **输入**：`uinput -T -c` 默认 click interval 100ms，总耗时约 250ms；传 `-c x y 10` 后约 155ms。`uitest uiInput click` 实测 1.9~2.0s，已不再用于点击。
- **端到端**：点击到画面更新 ≈ 输入 150~250ms + 等下一帧 0~450ms + 传输/解码约 50ms ≈ 0.2~0.8s。
- **已做优化**：PC 与 agent 的点击改 `uinput ... 10`，滑动 150ms；agent 抓图间隔默认 50ms；网页点击即时显示波纹，先给操作反馈。
- **进一步方案**：agent 直接写 `/dev/uinput`（省进程启动）；真正低延迟需系统级 `AVScreenCapture` + H264（需 system 权限/ROM）。
- 无音频；屏幕旋转/分辨率变化需重新取帧尺寸（当前每帧更新）。
- 键码已实测：uinput `-K` 用 OHOS 码，2=Back、1=Home；`uitest` 后台运行会挂住，不可用。

## 后续可选
- root native server（display HDI + H264 硬编 + hdc fport）提升到 30fps；强绑定 OH 版本。
- 文件拖拽、剪贴板同步、多设备平铺。

## 设备 agent（局域网原型，2026-11-17）

- `agent/`：Go 单文件，嵌入网页；HTTP 提供页面，WebSocket 推 JPEG 帧并接收输入。
- 已在设备 root 下验证：`snapshot_display` 必须用 `.jpeg` 后缀；`uitest` 脱离前台会挂住，输入改用 `uinput -T -c/-m`，键盘用 `uinput -K`（ASCII）。
- 实测：浏览器打开 `http://<设备IP>:8765/?token=...`，约 2fps、可点击/滑动；点击有即时波纹反馈。
- 待办：文本中文（需 IME/剪贴板）、返回键码验证、鉴权与 TLS、断线重连。


## agent（设备端）
- Go 静态二进制，HTTP 页面 + WebSocket 推帧；输入 uinput；ASCII 文本。
- 启动：`scripts/start-agent.ps1`；设备重启后需重新启动。
- 待办：中文输入（IME/剪贴板）、TLS/鉴权强化、断线重连、开机自启（需 init 服务）。
