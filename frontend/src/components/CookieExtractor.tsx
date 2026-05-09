import { useState } from 'react';
import { Button, Drawer, Typography, Space, Alert, Input, message, Tooltip } from 'antd';
import { CopyOutlined, ExportOutlined } from '@ant-design/icons';

const EXTRACT_SCRIPT = `(async function() {
  const cookies = document.cookie.split(';').filter(c => c.trim()).map(c => {
    const [name, ...rest] = c.trim().split('=');
    return {
      name: name.trim(),
      value: rest.join('=').trim(),
      domain: location.hostname,
      path: '/'
    };
  });

  const json = JSON.stringify(cookies, null, 2);

  try {
    await navigator.clipboard.writeText(json);
    console.log('%c✅ Cookie JSON 已复制到剪贴板！', 'color: #52c41a; font-size: 14px; font-weight: bold');
    console.log('%c现在回到 WebBot 页面，将 JSON 粘贴到 Cookies 输入框中', 'color: #8c8c8c');
  } catch (e) {
    console.log(json);
  }

  return json;
})();`;

export default function CookieExtractor() {
  const [open, setOpen] = useState(false);

  const handleCopyScript = () => {
    navigator.clipboard.writeText(EXTRACT_SCRIPT).then(() => {
      message.success('提取脚本已复制到剪贴板');
    });
  };

  const handleCopyTemplate = () => {
    const template = `[
  {
    "name": "sessionid",
    "value": "替换成你从浏览器复制的值",
    "domain": "www.example.com",
    "path": "/",
    "secure": true,
    "sameSite": "None",
    "httpOnly": true
  }
]`;
    navigator.clipboard.writeText(template).then(() => {
      message.success('模板已复制到剪贴板');
    });
  };

  return (
    <>
      <Tooltip title="从浏览器提取当前页面 Cookie">
        <Button size="small" icon={<ExportOutlined />} onClick={() => setOpen(true)}>
          一键提取
        </Button>
      </Tooltip>

      <Drawer
        title="Cookie 提取助手"
        open={open}
        onClose={() => setOpen(false)}
        width={540}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type="info"
            message="使用步骤"
            description={
              <ol style={{ paddingLeft: 16, margin: 0 }}>
                <li>在浏览器<strong>新标签页</strong>中打开你要测试的目标网页（并登录）</li>
                <li>按 <kbd>F12</kbd> 打开开发者工具，切换到 <strong>Console</strong> 标签</li>
                <li>点击下方「复制脚本」按钮，将脚本粘贴到 Console 中回车运行</li>
                <li>Cookie JSON 会自动复制到你的剪贴板</li>
                <li>关闭此助手，将 JSON 粘贴到 Cookies 输入框中即可</li>
              </ol>
            }
          />

          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <Typography.Text strong>提取脚本</Typography.Text>
              <Button
                icon={<CopyOutlined />}
                onClick={handleCopyScript}
                type="primary"
                size="small"
              >
                复制脚本
              </Button>
            </div>
            <Input.TextArea
              value={EXTRACT_SCRIPT}
              readOnly
              rows={14}
              style={{ fontFamily: 'monospace', fontSize: 12, background: '#f6ffed' }}
            />
          </div>

          <Alert
            type="warning"
            message="注意事项"
            description={
              <ul style={{ paddingLeft: 16, margin: 0 }}>
                <li>
                  此脚本只能提取<strong>非 HttpOnly</strong> 的 Cookie。如果目标网站使用
                  HttpOnly Cookie 维持登录态，你需要手动从 Application &gt; Cookies
                  面板中补充这些字段。
                </li>
                <li>
                  运行脚本前请确保你已在目标网站<strong>登录成功</strong>，并且当前页面 URL
                  与你要测试的 URL 属于同一域名。
                </li>
                <li>
                  如果提取的 Cookie 仍然无法登录，请检查 <code>sameSite</code> 和{' '}
                  <code>secure</code> 属性是否正确。
                </li>
              </ul>
            }
          />

          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <Typography.Text strong>手动填写模板（含完整字段）</Typography.Text>
              <Button icon={<CopyOutlined />} onClick={handleCopyTemplate} size="small">
                复制模板
              </Button>
            </div>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 4,
                fontSize: 12,
                overflow: 'auto',
                margin: 0,
              }}
            >
              {`[
  {
    "name": "sessionid",
    "value": "替换成你从浏览器复制的值",
    "domain": "www.example.com",
    "path": "/",
    "secure": true,
    "sameSite": "None",
    "httpOnly": true
  }
]`}
            </pre>
          </div>
        </Space>
      </Drawer>
    </>
  );
}
