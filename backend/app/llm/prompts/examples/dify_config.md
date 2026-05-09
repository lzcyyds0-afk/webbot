## Example: Dify Application Configuration

**Goal:** 在 Dify 中创建一个新应用并配置 LLM 模型为 GPT-4

**Page Context:**
- URL: https://cloud.dify.ai/apps
- Elements:
```
[button] "创建应用" selector=[data-testid="create-app-btn"] pos=(100,80)
[button] "聊天助手" selector=[data-testid="chat-assistant-option"] pos=(300,200)
[button] "创建" selector=[data-testid="confirm-create-btn"] pos=(500,400)
[textbox] "应用名称" selector=input[placeholder="给应用起个名字"] pos=(300,150)
[button] "设置" selector=[data-testid="settings-tab"] pos=(200,20)
[combobox] "模型" selector=[data-testid="model-select"] pos=(300,250)
[button] "保存" selector=[data-testid="save-settings-btn"] pos=(400,500)
```

**Expected Steps:**
```json
[
  {"action": "goto", "url": "https://cloud.dify.ai/apps"},
  {"action": "wait", "ms": 1500},
  {"action": "click", "selector": "[data-testid=\"create-app-btn\"]"},
  {"action": "wait", "ms": 500},
  {"action": "click", "selector": "[data-testid=\"chat-assistant-option\"]"},
  {"action": "wait", "ms": 300},
  {"action": "input", "selector": "input[placeholder=\"给应用起个名字\"]", "text": "Test Assistant"},
  {"action": "wait", "ms": 200},
  {"action": "click", "selector": "[data-testid=\"confirm-create-btn\"]"},
  {"action": "wait", "ms": 1000},
  {"action": "click", "selector": "[data-testid=\"settings-tab\"]"},
  {"action": "wait", "ms": 500},
  {"action": "click", "selector": "[data-testid=\"model-select\"]"},
  {"action": "wait", "ms": 300},
  {"action": "click", "selector": "option[value=\"gpt-4\"]"},
  {"action": "wait", "ms": 300},
  {"action": "click", "selector": "[data-testid=\"save-settings-btn\"]"},
  {"action": "wait", "ms": 800},
  {"action": "screenshot"}
]
```
