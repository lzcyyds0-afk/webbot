## Example: Coze Workflow Canvas

**Goal:** 新建一个工作流，拖入 LLM 节点并连接到开始节点

**Page Context:**
- URL: https://www.coze.cn/workflow
- Elements:
```
[button] "新建" selector=[data-testid="new-workflow-btn"] pos=(20,60)
[treeitem] "LLM" selector=[data-testid="llm-node"] pos=(20,200) draggable
[treeitem] "开始" selector=[data-testid="start-node"] pos=(20,140) draggable
[button] "保存" selector=[data-testid="save-btn"] pos=(700,10)
[button] "发布" selector=[data-testid="publish-btn"] pos=(790,10)
[generic] "画布" selector=#canvas pos=(200,50) size=800x600
```

**Expected Steps:**
```json
[
  {"action": "goto", "url": "https://www.coze.cn/workflow"},
  {"action": "wait", "ms": 1500},
  {"action": "click", "selector": "[data-testid=\"new-workflow-btn\"]"},
  {"action": "wait", "ms": 800},
  {"action": "drag", "from_selector": "[data-testid=\"llm-node\"]", "to_selector": "#canvas"},
  {"action": "wait", "ms": 500},
  {"action": "connect", "from_selector": "[data-testid=\"start-node\"]", "to_selector": "[data-testid=\"llm-node\"]"},
  {"action": "wait", "ms": 500},
  {"action": "click", "selector": "[data-testid=\"save-btn\"]"},
  {"action": "wait", "ms": 1000},
  {"action": "screenshot"}
]
```
