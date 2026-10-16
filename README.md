# Water Reminder

一个轻量的 Windows 桌面喝水提醒工具：托盘常驻、可关闭的悬浮小杯、本地饮水记录与可配置提醒。

A lightweight Windows tray app with a hideable floating cup, local drink tracking, and configurable reminders.

## 功能

- 从托盘菜单或悬浮小杯快速记录饮水，也可填写自定义容量。
- 查看当天累计饮水量、目标进度和下次提醒时间。
- 设置杯量、每日目标、提醒间隔、提醒时段和稍后提醒时长。
- 暂停提醒；隐藏悬浮杯不会退出托盘应用。
- 数据仅保存在本机，不创建账户，也不连接网络。

## 快速开始

需要 Windows 10/11 和 Python 3.10 或更高版本。项目 CI 覆盖 Python 3.10–3.12。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m water_reminder.main
```

## 默认设置

| 设置 | 默认值 |
| --- | ---: |
| 一杯容量 | 200 ml |
| 每日目标 | 1,600 ml |
| 提醒间隔 | 90 分钟 |
| 提醒时段 | 08:00–22:00 |
| 稍后提醒 | 10 分钟 |

这些值都可以在应用设置中调整。每日目标是个人设置，不构成医疗建议。只有用户确认后才会记录饮水；稍后提醒和隐藏悬浮杯不会增加饮水量。

## 本地数据

设置和饮水记录以 JSON 保存到 `%LOCALAPPDATA%\WaterReminder\water.json`。应用不上传数据。关闭应用后，可复制该文件进行备份。

## 开发与测试

```powershell
python -m pytest -q
```

提醒调度与数据存储逻辑可独立测试，Qt 界面有基础交互测试。每次推送和 Pull Request 都会在 Windows CI 上运行测试。

## 发布状态

当前发布的是源码，尚未提供通过启动验收的独立 Windows 可执行文件。不要将本地 `dist` 目录作为正式 Release 分发。

## 许可证

本仓库自有代码采用 MIT 许可证，见 [LICENSE](LICENSE)。PySide6/Qt 是独立的第三方依赖，其许可证不由本仓库许可证覆盖；分发打包版本前，请核对并满足依赖方的适用条款。

## 贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
