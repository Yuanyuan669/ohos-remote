# ohos-remote

PC 侧 OpenHarmony 远程查看/控制工具，走 hdc，无需设备端 App/系统签名。

## 现状（MVP）

- 设备发现（USB / hdc TCP）
- 实时画面：`snapshot_display` 截图循环（约 2~3 fps，1080x2408）
- 鼠标点击/拖拽 → `uinput`（click interval 10ms，低延迟）
- 文本发送 → `uitest uiInput inputText`
- 保存当前截图为 PNG
- 返回键：uinput `-K` 键码 **2=Back，1=Home**（本机已实测）

## 运行

```powershell
python -m pip install pillow
python src\app.py --fps 2.5
# 或指定设备/hdc：
python src\app.py --hdc D:\ohos-tools\sdk\openharmony-4.0-Release\toolchains\hdc.exe --target 192.168.31.175:5555
```

要求：设备已开启 hdc 调试（root/debuggable 更容易），`hdc list targets` 能看到设备。

## 限制

- 无音频；2~3 fps，适合操作/演示，不适合视频。抓图单帧约 400~450ms 是主要瓶颈。
- 依赖 `snapshot_display` / `uitest`，不同 OH 版本参数可能不同。
- hdc TCP 模式会暴露调试权限，注意网络安全。
- 完整设计见 `docs/PLAN.md`。


## 设备 agent（局域网/免 PC）

```powershell
# 推 agent 并后台启动（需要 hdc root；token 自定）
powershell -ExecutionPolicy Bypass -File scripts\start-agent.ps1 -Token 123456
# 手机/PC 浏览器打开脚本输出的 http://<IP>:8765/?token=123456
```

- WebSocket 推 JPEG 帧（约 2 fps），点击/滑动走 `uinput`，文本支持 **ASCII**（中文暂不支持）。
- agent 为 Go 静态二进制（`agent/`），设备重启后需重新启动；不放仓库（用 `go build` 生成）。
