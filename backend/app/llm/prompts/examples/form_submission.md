## Example: Registration Form Submission

**Goal:** 填写注册表单并提交

**Page Context:**
- URL: https://example.com/register
- Elements:
```
[textbox] "用户名" selector=input#username pos=(300,200)
[textbox] "邮箱" selector=input#email pos=(300,260)
[textbox] "密码" selector=input#password pos=(300,320)
[textbox] "确认密码" selector=input#confirm-password pos=(300,380)
[button] "注册" selector=button[type="submit"] pos=(300,450)
[link] "已有账号？登录" selector=a[href="/login"] pos=(300,500)
```

**Expected Steps:**
```json
[
  {"action": "goto", "url": "https://example.com/register"},
  {"action": "wait", "ms": 1000},
  {"action": "input", "selector": "input#username", "text": "testuser123"},
  {"action": "input", "selector": "input#email", "text": "test@example.com"},
  {"action": "input", "selector": "input#password", "text": "SecurePass123!"},
  {"action": "input", "selector": "input#confirm-password", "text": "SecurePass123!"},
  {"action": "wait", "ms": 300},
  {"action": "click", "selector": "button[type=\"submit\"]"},
  {"action": "wait", "ms": 1500},
  {"action": "screenshot"}
]
```
