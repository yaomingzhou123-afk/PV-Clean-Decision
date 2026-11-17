# 交付检查清单（DELIVERY_CHECKLIST）

生成时间：2026-11-17 · 基于 commit b4c40da + 五件套重组

## 一、五件套目录结构

| 目录 | 状态 | 文件数 | 说明 |
|---|---|---|---|
| `ppt/` | ✅ | 6 | PPTX + PDF + 演讲稿 + 问答参考 + 构建脚本 + screenshots/ |
| `project/` | ✅ | 80+ | 完整源码（backend/frontend/docs/tests）+ 配置 + 启动脚本 + CI |
| `video/` | ✅ | 1 | 功能演示视频（2:11 / H.264 / 4.4MB） |
| `codearts_proof/` | ✅ | 9 | 8 份开发记录 + screenshots/NEED.md |
| `readme/` | ✅ | 1 | README.md（含 14 节完整说明） |

## 二、PPT 检查

| 项 | 状态 | 说明 |
|---|---|---|
| PPTX 文件存在 | ✅ | `ppt/PV-Clean-Decision-答辩PPT.pptx`（1.1MB） |
| PDF 文件存在 | ✅ | `ppt/PV-Clean-Decision-答辩PPT.pdf`（1.2MB） |
| 页数 | ✅ | 14 页 |
| 含场景背景 | ✅ | 第 2 页 |
| 含功能架构 | ✅ | 第 4 页 |
| 含核心亮点 | ✅ | 第 11 页 |
| 含码道应用说明 | ⚠️ | **缺独立页**，需团队在 PPT 中补 1 页（内容可参考 readme/README.md"码道应用总结"章节） |

## 三、视频检查

| 项 | 状态 | 说明 |
|---|---|---|
| 视频文件存在 | ✅ | `video/PV-Clean-Decision-功能演示视频.mp4`（4.4MB） |
| 时长 ≤3 分钟 | ✅ | 2 分 11 秒 |
| 编码兼容 | ✅ | H.264 High，Windows 自带播放器可播 |
| 核心功能操作流程 | ✅ | 七 Agent 决策 + 模拟实验室 + 断网降级 + Agent 问答 |

## 四、源码检查

| 项 | 状态 | 说明 |
|---|---|---|
| backend/ 完整 | ✅ | 27 个源文件 + 18 个测试文件 |
| frontend/ 完整 | ✅ | index.html（1032 行） |
| 知识库 | ✅ | `project/backend/kb/knowledge.jsonl`（37 条） |
| 配置文件 | ✅ | `project/backend/data/pv_config.json` |
| 依赖清单 | ✅ | `project/requirements.txt` |
| 启动脚本 | ✅ | run.sh / run.bat / start.bat（路径已验证） |
| .env.example | ✅ | `project/.env.example` |
| .env 排除 | ✅ | .gitignore 排除，不进交付包 |
| CI 配置 | ✅ | 路径已更新为 project/ 前缀 |
| 测试通过 | ✅ | **210 passed**（30.33s） |

## 五、README 检查

| 章节 | 状态 |
|---|---|
| 项目背景 | ✅ |
| 核心功能 | ✅ |
| 系统架构 | ✅ |
| 七个 Agent 职责 | ✅ |
| Agent 协作机制 | ✅ |
| MCP 调用链路 | ✅ |
| RAG 机制 | ✅ |
| 数据来源及限制 | ✅ |
| 环境依赖 | ✅ |
| 安装方法 | ✅ |
| Windows 启动 | ✅ |
| Linux 部署 | ✅ |
| 测试方法 | ✅ |
| 开源组件说明 | ✅ |
| 码道应用总结 | ✅ |

## 六、启动脚本路径验证

| 脚本 | 位置 | 路径自洽 |
|---|---|---|
| run.sh | project/ | ✅ `cd backend` 相对 project/ 正确 |
| run.bat | project/ | ✅ `.venv` 在 project/，`cd backend` 后 `..\.venv` 正确 |
| start.bat | project/ | ✅ `.env` 在 project/，`cd backend` 正确 |
| launch.json | project/.vscode/ | ✅ `${workspaceFolder}/backend` 指向 project/backend |
| ci.yml | project/.github/ | ✅ 已更新为 `project/requirements.txt`、`project/backend/tests`、`project/frontend/index.html` |

## 七、不提交项验证

| 项 | 状态 |
|---|---|
| .env（含密钥） | ✅ 已排除 |
| .venv/ 虚拟环境 | ✅ 已排除 |
| __pycache__/ | ✅ 已排除 |
| .pytest_cache/ | ✅ 已排除 |
| review/（内部审查） | ⚠️ 未跟踪，不进交付包 |

## 八、待团队补齐项

| 项 | 优先级 | 说明 |
|---|---|---|
| PPT 补"码道应用说明"页 | 高 | 25 分权重，内容可从 readme/README.md"码道应用总结"提炼 |
| codearts_proof/screenshots/ 4 类真实截图 | 高 | 见 screenshots/NEED.md，需在码道客户端真实截取 |
| codearts_proof/03 更新测试数 | 中 | 停在 v2.7/49 项，实际 v3.0/210 项 |
| codearts_proof/07 部署记录 | 中 | 沙箱部署 3 项 ⬜ 待补（如已部署则补记录） |
| 撤销 MaaS API Key | 高 | 之前在对话中暴露，需在 MaaS 控制台撤销 |

## 九、打包命名

```
疆光-光伏电站沙尘清洗决策Agent-队伍名称-v1.0-联系方式.zip
```

打包时排除：.git/、review/、.env、.venv/、__pycache__/、.pytest_cache/

## 十、体积检查

| 项 | 大小 | 限制 |
|---|---|---|
| 交付包总体积 | ~57MB | ≤200MB ✅ |
| video/ | 4.4MB | - |
| ppt/ | ~7.9MB | - |
| project/ | ~1.5MB | - |
