# ohos-remote

PC 侧 OpenHarmony 远程查看/控制工具，走 hdc，无需设备端 App/系统签名。

## 现状（MVP）

- 设备发现（USB / hdc TCP）
- 实时画面：`snapshot_display` 截图循环（约 2~3 fps，1080x2408）
- 鼠标点击/拖拽 → `uitest uiInput click/swipe`
- 文本发送 → `uitest uiInput inputText`
- 保存当前截图为 PNG
- 返回键（`keyEvent 2`，待各机型验证）

## 运行

```powershell
python -m pip install pillow
python src\app.py --fps 2.5
# 或指定设备/hdc：
python src\app.py --hdc D:\ohos-tools\sdk\openharmony-4.0-Release\toolchains\hdc.exe --target 192.168.31.175:5555
```

要求：设备已开启 hdc 调试（root/debuggable 更容易），`hdc list targets` 能看到设备。

## 限制

- 无音频；2~3 fps，适合操作/演示，不适合视频。
- 依赖 `snapshot_display` / `uitest`，不同 OH 版本参数可能不同。
- hdc TCP 模式会暴露调试权限，注意网络安全。
- 完整设计见 `docs/PLAN.md`。
