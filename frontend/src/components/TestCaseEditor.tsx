import { useState, useRef, useCallback, useEffect } from 'react';
import { Button, Space, Dropdown, Typography, message, Popconfirm, Collapse } from 'antd';
import {
  PlayCircleOutlined,
  SaveOutlined,
  PlusOutlined,
  RobotOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { useProjectsStore } from '../stores/projectsStore';
import * as runsApi from '../api/runs';
import AIGenerateModal from './AIGenerateModal';
import TestCaseExplainDrawer from './TestCaseExplainDrawer';
import type { TestCase, StepDef } from '../types';

const { Title } = Typography;

// ── Action templates for quick insert ──
const ACTION_TEMPLATES: Record<string, StepDef> = {
  goto: { action: 'goto', url: '/path' },
  click: { action: 'click', selector: '' },
  input: { action: 'input', selector: '', text: '' },
  wait: { action: 'wait', ms: 1000 },
  screenshot: { action: 'screenshot', full_page: false },
  drag: { action: 'drag', from_selector: '', to_point: { x: 600, y: 400 } },
  connect: { action: 'connect', from_port_selector: '', to_port_selector: '' },
};

const COOKIE_TEMPLATE = `[
  {
    "name": "sessionid",
    "value": "your-session-value",
    "domain": "example.com",
    "path": "/",
    "secure": true,
    "sameSite": "Lax"
  }
]`;

// ── Bookmarklet: one-click cookie extraction ──
// Minified JS that users can drag to their bookmarks bar
const BOOKMARKLET_JS = encodeURIComponent(
  "(function(){var c=document.cookie.split(';').filter(function(x){return x.trim()}).map(function(x){var p=x.trim().split('=');return{name:p[0].trim(),value:p.slice(1).join('=').trim(),domain:location.hostname,path:'/'}});var j=JSON.stringify(c,null,2);navigator.clipboard.writeText(j).then(function(){alert('Cookies copied! Paste into WebBot.')}).catch(function(){prompt('Copy this JSON:',j)});})();"
);
const BOOKMARKLET_URL = `javascript:${BOOKMARKLET_JS}`;

interface Props {
  projectId: number;
  testCase: TestCase;
}

export default function TestCaseEditor({ projectId, testCase }: Props) {
  const navigate = useNavigate();
  const updateTestCaseSteps = useProjectsStore((s) => s.updateTestCaseSteps);
  const currentProject = useProjectsStore((s) => s.currentProject);
  const editorRef = useRef<any>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [jsonText, setJsonText] = useState(
    JSON.stringify(testCase.steps_json, null, 2),
  );
  const [cookieText, setCookieText] = useState(
    JSON.stringify(testCase.cookies_json ?? [], null, 2),
  );
  const [cookieExpanded, setCookieExpanded] = useState(false);

  // Sync editor content when switching test cases
  useEffect(() => {
    setJsonText(JSON.stringify(testCase.steps_json, null, 2));
    setCookieText(JSON.stringify(testCase.cookies_json ?? [], null, 2));
  }, [testCase.id]);

  const handleEditorMount = (editor: any) => {
    editorRef.current = editor;
  };

  // ── Validate & parse JSON ──
  const parseSteps = (): StepDef[] | null => {
    try {
      const parsed = JSON.parse(jsonText);
      if (!Array.isArray(parsed)) {
        message.error('JSON 必须是数组');
        return null;
      }
      return parsed;
    } catch (e: any) {
      message.error(`JSON 语法错误: ${e.message}`);
      return null;
    }
  };

  const parseCookies = (): TestCase['cookies_json'] => {
    const text = cookieText.trim();
    if (!text || text === '[]' || text === 'null') return null;
    try {
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed)) {
        message.error('Cookie JSON 必须是数组');
        return undefined;
      }
      return parsed;
    } catch (e: any) {
      message.error(`Cookie JSON 语法错误: ${e.message}`);
      return undefined;
    }
  };

  // ── Save ──
  const handleSave = async () => {
    const steps = parseSteps();
    if (!steps) return;
    const cookies = parseCookies();
    if (cookies === undefined) return;
    setSaving(true);
    try {
      await updateTestCaseSteps(projectId, testCase.id, steps, cookies);
      message.success('已保存');
    } finally {
      setSaving(false);
    }
  };

  // ── Run ──
  const handleRun = async () => {
    const steps = parseSteps();
    if (!steps) return;
    const cookies = parseCookies();
    if (cookies === undefined) return;
    setRunning(true);
    try {
      // Save first
      await updateTestCaseSteps(projectId, testCase.id, steps, cookies);
      // Then create run
      const run = await runsApi.createRun({ test_case_id: testCase.id });
      message.success('运行已启动');
      navigate(`/runs/${run.id}`);
    } catch {
      // error handled by interceptor
    } finally {
      setRunning(false);
    }
  };

  // ── Navigate to step in editor ──
  const handleNavigateToStep = useCallback((stepIndex: number) => {
    const editor = editorRef.current;
    if (!editor) return;
    const model = editor.getModel();
    if (!model) return;
    const lines = model.getLinesContent();
    let found = 0;
    let targetLine = 1;
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].trim().startsWith('"action"')) {
        if (found === stepIndex) {
          targetLine = i + 1;
          break;
        }
        found++;
      }
    }
    editor.setPosition({ lineNumber: targetLine, column: 1 });
    editor.revealLineInCenter(targetLine);
    editor.focus();
    setExplainOpen(false);
  }, []);

  // ── Quick insert action ──
  const handleInsertAction = useCallback((actionType: string) => {
    const template = ACTION_TEMPLATES[actionType];
    if (!template) return;
    const editor = editorRef.current;
    if (!editor) {
      // Fallback: append to JSON
      try {
        const arr = JSON.parse(jsonText);
        arr.push(template);
        setJsonText(JSON.stringify(arr, null, 2));
      } catch {
        setJsonText(JSON.stringify([template], null, 2));
      }
      return;
    }
    // Use editor command to insert at cursor
    const pos = editor.getPosition();
    const range = {
      startLineNumber: pos.lineNumber,
      startColumn: pos.column,
      endLineNumber: pos.lineNumber,
      endColumn: pos.column,
    };
    const insertText = JSON.stringify(template, null, 2);
    editor.executeEdits('insert-action', [{ range, text: insertText }]);
  }, [jsonText]);

  const handlePasteTemplate = () => {
    setCookieText(COOKIE_TEMPLATE);
    message.success('已填入 Cookie 模板');
  };

  const handleCopyExtractScript = () => {
    navigator.clipboard.writeText(BOOKMARKLET_URL).then(() => {
      message.success('书签链接已复制，按提示添加到浏览器书签栏即可');
    });
  };

  const dropdownItems = Object.keys(ACTION_TEMPLATES).map((key) => ({
    key,
    label: key,
  }));

  const collapseItems = [
    {
      key: 'cookies',
      label: (
        <span>
          Cookie 配置
          {testCase.cookies_json && testCase.cookies_json.length > 0 && (
            <span style={{ color: '#52c41a', marginLeft: 8, fontSize: 12 }}>
              ({testCase.cookies_json.length} 条)
            </span>
          )}
        </span>
      ),
      children: (
        <div>
          {/* Bookmarklet */}
          <div style={{ background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6, padding: 12, marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography.Text strong style={{ color: '#389e0d' }}>
                方式一：书签小工具（一键提取非 HttpOnly Cookie）
              </Typography.Text>
              <Button size="small" type="primary" ghost onClick={handleCopyExtractScript}>
                复制书签链接
              </Button>
            </div>
            <ol style={{ paddingLeft: 16, margin: '8px 0 0', fontSize: 12, color: '#595959' }}>
              <li>点击上方「复制书签链接」按钮</li>
              <li>在浏览器中按 <kbd>Ctrl+D</kbd>（或点击地址栏右侧的⭐）添加书签</li>
              <li>书签名称随意，把<strong>网址/URL 替换成刚才复制的内容</strong></li>
              <li>在目标网站点一下这个书签，非 HttpOnly Cookie 自动复制到剪贴板</li>
            </ol>
            <Typography.Text type="warning" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
              ⚠️ 书签工具<strong>读不到 HttpOnly Cookie</strong>。如果目标网站用 HttpOnly Cookie 维持登录（如 Coze、GitHub、多数企业系统），请用方式二。
            </Typography.Text>
          </div>

          {/* Manual fallback */}
          <div style={{ background: '#fff7e6', border: '1px solid #ffd591', borderRadius: 6, padding: 12, marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography.Text strong style={{ color: '#d46b08' }}>
                方式二：手动复制（支持 HttpOnly，推荐用于 Coze 等需要登录的网站）
              </Typography.Text>
              <Space>
                <Button size="small" onClick={handlePasteTemplate}>
                  填入模板
                </Button>
              </Space>
            </div>
            <ol style={{ paddingLeft: 16, margin: '8px 0 0', fontSize: 12, color: '#595959' }}>
              <li>在浏览器中<strong>登录目标网站</strong>（如 coze.cn），确保登录成功</li>
              <li>按 F12 打开开发者工具 → 切换到 <strong>Application（应用）</strong> 标签</li>
              <li>左侧展开 <strong>Cookies</strong> → 点击目标域名（如 <code>coze.cn</code>）</li>
              <li>找到维持登录态的关键 Cookie，通常名称是 <code>sessionid</code>、<code>token</code>、<code>sso_token</code> 等</li>
              <li>把 <strong>Name、Value、Domain、Path</strong> 填入下方 JSON 编辑器（Value 必须完整复制）</li>
            </ol>
            <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
              💡 <strong>Domain 注意：</strong>DevTools 里显示 <code>.coze.cn</code>（带点）就保留点；显示 <code>coze.cn</code> 就不带。填错域名 Cookie 不会生效。
            </Typography.Text>
          </div>
          <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, overflow: 'hidden', height: 160 }}>
            <Editor
              height="100%"
              language="json"
              theme="vs"
              value={cookieText}
              onChange={(v) => setCookieText(v ?? '[]')}
              options={{
                minimap: { enabled: false },
                fontSize: 12,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 2,
                padding: { top: 4 },
              }}
            />
          </div>
        </div>
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Title level={4} style={{ margin: 0 }}>{testCase.name}</Title>
        <Space>
          <Button
            icon={<RobotOutlined />}
            onClick={() => setAiModalOpen(true)}
          >
            AI 生成
          </Button>
          <Button
            icon={<EyeOutlined />}
            onClick={() => setExplainOpen(true)}
          >
            AI 预演
          </Button>
          <Dropdown
            menu={{ items: dropdownItems, onClick: ({ key }) => handleInsertAction(key) }}
          >
            <Button icon={<PlusOutlined />}>插入动作</Button>
          </Dropdown>
          <Button icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            保存
          </Button>
          <Popconfirm
            title="运行该用例？"
            description="将先保存当前编辑内容，然后启动运行"
            onConfirm={handleRun}
            okText="运行"
            cancelText="取消"
          >
            <Button type="primary" icon={<PlayCircleOutlined />} loading={running}>
              运行
            </Button>
          </Popconfirm>
        </Space>
      </div>

      {/* Monaco Editor */}
      <div style={{ flex: 1, border: '1px solid #d9d9d9', borderRadius: 6, overflow: 'hidden', minHeight: 200 }}>
        <Editor
          height="100%"
          language="json"
          theme="vs"
          value={jsonText}
          onChange={(v) => setJsonText(v ?? '[]')}
          onMount={handleEditorMount}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            padding: { top: 8 },
          }}
        />
      </div>

      {/* Cookie Config */}
      <div style={{ marginTop: 8 }}>
        <Collapse
          activeKey={cookieExpanded ? ['cookies'] : []}
          onChange={(keys) => setCookieExpanded(keys.includes('cookies'))}
          items={collapseItems}
          ghost
        />
      </div>

      {/* AI Generate Modal */}
      <AIGenerateModal
        open={aiModalOpen}
        projectId={projectId}
        baseUrl={currentProject?.base_url ?? ''}
        onClose={(steps) => {
          setAiModalOpen(false);
          if (steps) {
            setJsonText(JSON.stringify(steps, null, 2));
            message.success(`已生成 ${steps.length} 个步骤，可在编辑器中调整`);
          }
        }}
      />

      {/* AI Explain Drawer */}
      <TestCaseExplainDrawer
        open={explainOpen}
        onClose={() => setExplainOpen(false)}
        projectId={projectId}
        caseId={testCase.id}
        caseName={testCase.name}
        onNavigateToStep={handleNavigateToStep}
      />
    </div>
  );
}
