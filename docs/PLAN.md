# ohos-remote 规划

## 目标
PC（先 Windows）远程查看并控制 OpenHarmony 设备；不依赖系统签名、不做设备端 App。

## 里程碑
- **M0（完成）**：hdc 封装、设备列表、模型读取。
- **M1（完成）**：截图循环 + Tkinter 显示 + FPS/延迟状态。
- **M2（完成）**：点击/拖拽/文本注入（uitest）；返回键待验证。
- **M3（进行中）**：文件 push/pull、应用安装、shell、日志面板。
- **M4**：无线（hdc tconn/tmode）、打包（PyInstaller）、多设备。

## 架构
```
src/hdc.py    hdc 子进程封装（serialize、超时、错误）
src/mirror.py 后台截图线程 → queue（丢旧帧）
src/app.py    Tkinter UI、坐标映射、输入事件
```
截图路径：`snapshot_display -f /data/local/tmp/ohosremote_*.jpeg` → `hdc file recv` → Pillow 解码。

## 已知限制
- 2~3 fps（JPEG 编码+传输）；无音频；延迟 300~500ms。
- 输入依赖 `uitest`；uinput 可作备选。
- 屏幕旋转/分辨率变化需重新取帧尺寸（当前每帧更新）。
- 返回键码 2 仅为假设，需实测。

## 后续可选
- root native server（display HDI + H264 硬编 + hdc fport）提升到 30fps；强绑定 OH 版本。
- 文件拖拽、剪贴板同步、多设备平铺。

## 设备 agent（局域网原型，2026-11-17）

- `agent/`：Go 单文件，嵌入网页；HTTP 提供页面，WebSocket 推 JPEG 帧并接收输入。
- 已在设备 root 下验证：`snapshot_display` 必须用 `.jpeg` 后缀；`uitest` 脱离前台会挂住，输入改用 `uinput -T -c/-m`，键盘用 `uinput -K`（ASCII）。
- 实测：浏览器打开 `http://<设备IP>:8765/?token=...`，1.9fps、可点击/滑动。
- 待办：文本中文（需 IME/剪贴板）、返回键码验证、鉴权与 TLS、断线重连。
