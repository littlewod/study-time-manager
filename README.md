<div align="center">
  <img src="assets/study-card-icon.png" width="128" alt="研途 Study Hub 图标">
  <h1>研途 Study Hub</h1>
  <p>本地优先的学习计划、专注计时与时间复盘工具。</p>
  <a href="https://github.com/littlewod/study-time-manager/actions/workflows/tests.yml"><img src="https://github.com/littlewod/study-time-manager/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
</div>

## 为什么做这个工具

普通待办清单只回答“做没做”，研途还会记录“计划投入多少时间、实际专注了多久”。它把每日任务、专注倒计时、周进度和阶段路线放在同一个轻量工具里，适合考研、语言学习、课程自学和长期技能训练。

所有计划与进度默认只保存在你的电脑上。项目不需要注册账号、不依赖云服务，也不会上传学习数据。

## 功能

- 今日学习卡：显示重点、待完成任务、剩余计划时长和完成进度。
- 专注计时：支持 25、45、60 分钟预设，暂停、继续、提前结束和自动记录。
- 时间复盘：统计今日专注分钟、专注次数，以及实际投入与计划时长的比例。
- 周视图与路线图：查看每天完成率、周目标和阶段安排。
- 桌面悬浮卡：Windows 高 DPI 清晰显示，可直接打卡并与网页端同步。
- 本地优先：断网时仍可使用，恢复连接后自动同步离线专注记录。
- 数据迁移：支持完整导入、导出任务进度和专注记录。
- PWA：网页端可安装，并缓存基础界面供离线查看。

## 快速开始

要求：Python 3.10 或更高版本。程序只使用 Python 标准库，没有第三方运行依赖。

```powershell
git clone https://github.com/littlewod/study-time-manager.git
cd study-time-manager
python desktop_widget.pyw
```

Windows 用户也可以双击 `start-study-hub.cmd`。首次启动会根据 [`examples/plan.example.json`](examples/plan.example.json) 自动生成一份从当天开始的 7 天示例计划，然后在屏幕右上角显示桌面学习卡。

点击卡片底部的“完整视图”，即可打开时间管理面板。默认地址是 <http://127.0.0.1:8765/>。

## 使用自己的计划

个人数据位于 `data/`，该目录中的 JSON 文件已被 Git 忽略，不会意外提交到公开仓库。

1. 首次运行程序，生成 `data/plan.json` 和 `data/progress.json`。
2. 参考 [`examples/plan.example.json`](examples/plan.example.json) 编辑任务、日期、分类和预计时长。
3. 重启桌面学习卡。网页端与桌面卡会读取同一份计划和进度。

每项任务至少需要以下字段：

```json
{
  "id": "unique-task-id",
  "category": "核心学习",
  "durationMin": 45,
  "title": "完成一节课程",
  "details": "学习任务说明",
  "acceptance": "可检查的完成标准"
}
```

## 数据与隐私

运行时会生成以下私有文件：

- `data/plan.json`：个人学习计划。
- `data/progress.json`：完成任务、笔记和专注时段。
- `plan-data.js`：供离线网页读取的本地计划副本。
- `study-hub.log`：本地服务日志。

这些文件均在 `.gitignore` 中。发布或提交代码前仍建议运行 `git status` 再次确认。

## 配置

可通过环境变量调整本地服务：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `STUDY_HUB_HOST` | `127.0.0.1` | 监听地址 |
| `STUDY_HUB_PORT` | `8765` | 本地端口 |
| `STUDY_HUB_REFRESH_MS` | `5000` | 桌面卡刷新间隔 |

## 项目结构

```text
study_hub/
  planning/           # 学习计划服务与 JSON 仓储
  bootstrap.py        # 首次启动与示例数据初始化
  http_server.py      # 本地 REST API 与静态资源服务
  widget.py           # Windows 桌面学习卡
examples/             # 可公开的示例计划与进度
tests/                # 服务、接口、初始化和关闭流程测试
index.html            # 时间管理面板
app.js                # 前端交互、专注计时与同步
styles.css            # 响应式界面
desktop_widget.pyw    # 应用入口
```

核心接口：

- `GET /health`、`GET /ready`
- `GET /api/v1/plan`
- `GET|PUT /api/v1/progress`
- `PATCH /api/v1/tasks/{taskId}`
- `POST /api/v1/focus-sessions`

## 开发与测试

```powershell
python -m unittest discover -s tests -v
node --check app.js
python desktop_widget.pyw --check
```

GitHub Actions 会在 Windows 和 Python 3.13 环境下执行同一组检查。

## 设计原则

- 本地优先：默认不依赖账号和云端。
- 真实反馈：同时关注任务完成率和实际专注时间。
- 低摩擦：打开即可用，减少为了管理学习而管理工具的时间。
- 可迁移：计划与进度都是可读、可导出的 JSON。

## License

[MIT](LICENSE)
