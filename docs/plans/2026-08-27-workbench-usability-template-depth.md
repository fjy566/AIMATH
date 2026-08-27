# 学习工作台易用性与答题模板深化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在保留现有功能和数据兼容性的前提下，让 68 个数学二细分题型更容易查找、理解、套写和进入专项训练，并降低工作台前端的重复渲染代码。

**Architecture:** 继续使用 FastAPI、SQLite、原生 JavaScript 与 KaTeX。后端以现有 68 个细分题型的目标、条件、方法、检查项和信号为事实源，统一生成更完整的命题覆盖、题型适配、训练层级和检查清单；前端只负责复用式呈现与交互，不复制学科规则。用户已有的模板覆盖字段保持兼容，新字段由当前模板实时派生。

**Tech Stack:** Python 3.12、FastAPI、SQLite、vanilla JavaScript、CSS、KaTeX、pytest。

---

### Task 1: 建立模板完整度回归基线

**Files:**
- Modify: `tests/test_core.py`

1. 为全部 68 个细分题型断言唯一 ID、必要字段、命题方向、题型策略、训练层级和检查清单。
2. 断言答题纸结构覆盖定位、条件、主过程与结论复核，且旧模板覆盖仍可正常应用。
3. 先运行相关测试，确认新断言在实现前失败。

### Task 2: 统一生成更详细的题型学习模板

**Files:**
- Modify: `app/services/workbench.py`

1. 从每个题型已有的目标、条件、方法、复核要求和信号中生成“如何识别”。
2. 为每个题型生成直接计算、参数分类、逆向证明、跨知识串联和易错伪装等命题方向，并结合所属知识块给出具体综合方向。
3. 分别给选择题、填空题和解答题提供适用的作答策略与验收标准。
4. 生成基础识别、标准执行、综合迁移三层训练路径和考场检查清单。
5. 将答题纸结构扩展为更细的得分链，同时保持旧 API 字段与自定义模板兼容。

### Task 3: 优化工作台查找、阅读和行动路径

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`

1. 在细分题型区域加入当前知识块内的即时筛选、结果计数和键盘方向键切换。
2. 在模板顶部加入段落导航、复制答题骨架和一键专项训练。
3. 呈现题型识别、命题方向、分题型策略、训练层级和检查清单，并用清晰的信息层级避免一次性阅读负担。
4. 把模板指南、例题区、变式区和事件绑定拆为可复用函数，减少超长字符串与重复监听代码。
5. 补齐加载、无匹配、复制失败、禁用、键盘焦点和窄屏状态。

### Task 4: 文档、验证与启动

**Files:**
- Modify: `README.md`
- Modify: `tests/test_core.py`

1. 更新工作台能力说明与 68 个题型模板口径。
2. 运行 Python 测试、编译检查、JavaScript 语法检查、diff 检查和 Impeccable 单次检测。
3. 启动本地后台，验证健康接口与工作台 API，打开应用供人工检查。
