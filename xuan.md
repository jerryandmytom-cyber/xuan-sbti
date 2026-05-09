# xuan_codex_upgrade.md
# FortuneMaster 系统商业化升级方案（Codex工程版）

---

# 一、项目目标

在现有系统基础上（fortunemaster.py + fortunemastervip.py）：

实现从：
👉 命理计算工具  
升级为：
👉 AI驱动的“决策 + 情绪 + 转化”商业系统

---

# 二、现有系统能力（基础）

## 1. 命理引擎（fortunemaster.py）

已具备：
- 八字计算（年/月/日/时）
- 五行分析（含藏干）
- 十神、格局、喜用神
- 冲合刑害
- 起运年龄

👉 结论：无需重写，直接复用

---

## 2. Telegram Bot（fortunemastervip.py）

已具备：
- 用户状态管理（TTL）
- 关键词触发付费
- 多服务（合婚/紫微/取名）

👉 问题：缺乏“转化逻辑”

---

# 三、核心升级思路

## ❌ 当前模式

算命 → 输出 → 收费

---

## ✅ 新模式

免费 → 半结果 → 心理钩子 → 解锁 → 依赖 → 咨询

---

# 四、系统新增模块（必须实现）

```json
{
  "new_modules": [
    "explainable_engine.py",
    "conversion_engine.py",
    "behavior_tracker.py",
    "consulting_trigger.py",
    "prompt_templates.py"
  ]
}
```

---

# 五、Explainable AI（核心升级）

## 目标
解决“用户不信任”

## 新增函数

```python
def build_explainable_output(result):
    return {
        "结论": result["summary"],
        "原因": result["logic"],
        "概率": "60%-80%",
        "建议": result["advice"]
    }
```

## 改造点

原：
```python
return result
```

改为：
```python
result = generate_bazi_detail(...)
return build_explainable_output(result)
```

---

# 六、免费转付费系统（关键盈利点）

## 新增：部分结果生成

```python
def generate_partial_report(full_report):
    return {
        "visible": full_report[:30],
        "locked": [
            "未来趋势",
            "风险节点",
            "关键决策"
        ],
        "cta": "解锁完整分析"
    }
```

---

## Bot接入逻辑

```python
if not is_paid(user):
    result = generate_partial_report(report)
else:
    result = report
```

---

# 七、行为追踪系统（必须加）

## 数据库新增

```sql
CREATE TABLE user_events (
    id SERIAL PRIMARY KEY,
    user_id INT,
    action TEXT,
    created_at TIMESTAMP
);
```

---

## Python记录行为

```python
def track_event(user_id, action):
    insert into user_events ...
```

---

## 记录关键行为

- 查看报告
- 点击付费
- 重复提问

---

# 八、咨询触发系统（利润核心）

## 逻辑

```python
def should_trigger_consulting(user):
    if user.view_count >= 3:
        return True
    if user.repeat_question:
        return True
    return False
```

---

## Bot触发

```python
if should_trigger_consulting(user):
    send_message("你的情况较复杂，建议深度分析")
```

---

# 九、Prompt系统（核心资产）

## Prompt模板

```text
你不是算命师，而是人生决策分析师

根据用户信息：
1. 输出人格特征（具体）
2. 当前问题（共鸣）
3. 未来趋势（概率）
4. 行动建议（可执行）

要求：
- 避免绝对预测
- 使用“你可能会”
- 必须具体
```

---

# 十、报告结构（必须统一）

## 完整报告

```
1. 人格分析
2. 当前问题
3. 未来趋势（时间线）
4. 风险提示
5. 决策建议
```

---

## 免费报告

```
1. 人格（部分）
2. 当前问题（完整）
3. 趋势（一句话）
4. 后续锁住
```

---

# 十一、转化设计（关键）

## 免费 → 付费

- 显示：已解锁30%
- 提示：关键内容未解锁
- 制造悬念

---

## 付费 → 咨询

- 提示：情况复杂
- AI有限
- 推荐真人

---

# 十二、代码集成点（必须按此改）

## 原函数

```python
generate_bazi_detail()
```

## 新流程

```python
generate_bazi_detail()
→ explainable_engine()
→ partial_report()
→ conversion_trigger()
```

---

# 十三、Bot增强逻辑

## 新增判断

```python
if user_repeat_question:
    push_payment()

if user_high_interest:
    push_consulting()
```

---

# 十四、上线优先级

## 第一阶段（必须）
- 免费结果 + 锁内容
- 支付接口
- 基础报告

## 第二阶段
- 行为追踪
- 咨询触发

## 第三阶段
- 个性化推荐
- AI优化

---

# 十五、最终系统结构

```json
{
  "input": "用户问题",
  "engine": "命理计算",
  "layer1": "AI解释",
  "layer2": "部分输出",
  "layer3": "转化系统",
  "output": "付费/订阅/咨询"
}
```

---

# 十六、核心商业本质（必须理解）

你不是在做：

❌ 算命工具  

你是在做：

✅ 情绪 + 决策 + 确定性产品  

---

# 十七、一句话总结

👉 用户买的不是“命运”  
👉 是“确定感 + 安心 + 指导”
