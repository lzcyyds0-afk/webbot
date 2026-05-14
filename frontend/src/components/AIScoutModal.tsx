import { useState } from 'react';
import {
  Modal,
  Form,
  Input,
  Alert,
  Spin,
  Typography,
  Space,
  Tag,
  Button,
  Card,
  Collapse,
  message,
} from 'antd';
import {
  CompassOutlined,
  SaveOutlined,
  EditOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { useProjectsStore } from '../stores/projectsStore';
import { scoutPage, type ScoutRequest } from '../api/scout';
import type { ScoutResponse, ScoutPath, StepDef } from '../types';
import CookieExtractor from './CookieExtractor';

const { Text, Paragraph } = Typography;

interface Props {
  open: boolean;
  projectId: number;
  baseUrl: string;
  onClose: () => void;
}

const RISK_COLORS: Record<number, string> = {
  1: '#52c41a',
  2: '#52c41a',
  3: '#faad14',
  4: '#ff4d4f',
  5: '#ff4d4f',
};

const RISK_LABELS: Record<number, string> = {
  1: '低',
  2: '低',
  3: '中',
  4: '高',
  5: '高',
};

export default function AIScoutModal({ open, projectId, baseUrl, onClose }: Props) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScoutResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());

  const createTestCase = useProjectsStore((s) => s.createTestCase);
  const updateTestCaseSteps = useProjectsStore((s) => s.updateTestCaseSteps);
  const fetchTestCases = useProjectsStore((s) => s.fetchTestCases);
  const setCurrentTestCase = useProjectsStore((s) => s.setCurrentTestCase);

  const handleStart = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      setError(null);
      setResult(null);

      const req: ScoutRequest = {
        url: values.url,
        goal: values.goal || undefined,
        cookies: values.cookies_json ? JSON.parse(values.cookies_json) : undefined,
      };

      const resp = await scoutPage(req);
      setResult(resp);
    } catch (e: any) {
      if (e?.errorFields) return;
      setError(e?.response?.data?.detail || e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    onClose();
    setTimeout(() => {
      setResult(null);
      setError(null);
      setSavingIds(new Set());
    }, 300);
  };

  // editedSteps: optional override from inline editor
  const handleSaveAsTestCase = async (
    path: ScoutPath,
    index: number,
    editedSteps?: StepDef[],
  ) => {
    setSavingIds((prev) => new Set(prev).add(index));
    try {
      const stepsToSave = editedSteps ?? path.steps;
      const tc = await createTestCase(projectId, { name: path.title });
      await updateTestCaseSteps(projectId, tc.id, stepsToSave);
      await fetchTestCases(projectId);
      setCurrentTestCase(tc);
      message.success(`已保存为用例: ${path.title}`);
      // Auto-close so user lands directly in the test case editor
      handleCancel();
    } catch (e: any) {
      message.error(e?.message || '保存失败');
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(index);
        return next;
      });
    }
  };

  return (
    <Modal
      title={
        <Space>
          <CompassOutlined />
          <span>AI 探索页面</span>
        </Space>
      }
      open={open}
      onCancel={handleCancel}
      width={760}
      footer={
        result?.paths
          ? [
              <Button key="back" onClick={() => setResult(null)}>
                重新探索
              </Button>,
              <Button key="close" onClick={handleCancel}>
                关闭
              </Button>,
            ]
          : [
              <Button key="cancel" onClick={handleCancel}>
                取消
              </Button>,
              <Button
                key="scout"
                type="primary"
                icon={<CompassOutlined />}
                onClick={handleStart}
                loading={loading}
              >
                {loading ? '探索中...' : '开始探索'}
              </Button>,
            ]
      }
      destroyOnClose
    >
      {/* Input form */}
      {!result && (
        <Form form={form} layout="vertical" initialValues={{ url: baseUrl }}>
          <Form.Item
            name="url"
            label="页面 URL"
            rules={[
              { required: true, message: '请输入 URL' },
              { type: 'url', message: '请输入合法 URL' },
            ]}
          >
            <Input placeholder="https://app.example.com/page" />
          </Form.Item>

          <Form.Item name="goal" label="探索目标（可选）">
            <Input.TextArea
              rows={2}
              placeholder="例如：重点测试登录和表单提交，留空则全面探索"
            />
          </Form.Item>

          <Alert
            type="warning"
            showIcon
            message="如果目标页面需要登录，必须配置 Cookie，否则 AI 只能看到登录页"
            style={{ marginBottom: 12 }}
            action={<CookieExtractor />}
          />

          <Form.Item
            name="cookies_json"
            label={
              <Space>
                <span>Cookies (JSON)</span>
                <Tag color="orange">登录页必填</Tag>
              </Space>
            }
            rules={[
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    const parsed = JSON.parse(value);
                    if (!Array.isArray(parsed)) return Promise.reject('必须是 JSON 数组');
                    return Promise.resolve();
                  } catch {
                    return Promise.reject('必须是合法 JSON');
                  }
                },
              },
            ]}
          >
            <Input.TextArea
              rows={3}
              placeholder='[{"name":"sessionid", "value":"xxx", "domain":"coze.cn", "path":"/", "httpOnly": true, "secure": true}]'
            />
          </Form.Item>
        </Form>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">
              正在打开页面、截图、识别交互元素、调用 Vision LLM 生成测试建议...
            </Text>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <Alert
          type="error"
          message="探索失败"
          description={error}
          style={{ marginBottom: 16 }}
          showIcon
        />
      )}

      {/* Result cards */}
      {result && (
        <div>
          <Alert
            type="success"
            message={`识别到 ${result.elements_count} 个交互元素，生成 ${result.paths.length} 条测试建议${result.retry_used ? '（经过一次修正）' : ''}`}
            style={{ marginBottom: 16 }}
            showIcon
          />

          <div style={{ marginBottom: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              页面: {result.page_title || result.url}
            </Text>
          </div>

          <Alert
            type="info"
            showIcon
            message='点击「保存为用例」后将自动跳转到编辑器，可在那里用「AI 精调」进一步修改步骤。'
            style={{ marginBottom: 16 }}
          />

          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {result.paths.map((path, idx) => (
              <PathCard
                key={idx}
                path={path}
                index={idx}
                onSave={(editedSteps) => handleSaveAsTestCase(path, idx, editedSteps)}
                saving={savingIds.has(idx)}
              />
            ))}
          </Space>
        </div>
      )}
    </Modal>
  );
}

// ── PathCard ──

function PathCard({
  path,
  index,
  onSave,
  saving,
}: {
  path: ScoutPath;
  index: number;
  onSave: (editedSteps?: StepDef[]) => void;
  saving: boolean;
}) {
  const riskColor = RISK_COLORS[path.risk_level] || '#52c41a';
  const riskLabel = RISK_LABELS[path.risk_level] || '低';
  const stepSummary = path.steps
    .slice(0, 5)
    .map((s) => s.action)
    .join(' → ');

  // Inline JSON editing state
  const [editingJson, setEditingJson] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const handleEditToggle = () => {
    if (editingJson === null) {
      setEditingJson(JSON.stringify(path.steps, null, 2));
      setJsonError(null);
    } else {
      setEditingJson(null);
      setJsonError(null);
    }
  };

  const handleSaveEdited = () => {
    try {
      const parsed = JSON.parse(editingJson!);
      if (!Array.isArray(parsed)) {
        setJsonError('必须是 JSON 数组');
        return;
      }
      onSave(parsed as StepDef[]);
    } catch {
      setJsonError('JSON 格式错误，请检查语法');
    }
  };

  return (
    <Card
      size="small"
      style={{ borderLeft: `4px solid ${riskColor}`, borderRadius: 6 }}
      bodyStyle={{ padding: '12px 16px' }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 8,
        }}
      >
        <Space direction="vertical" size={0} style={{ flex: 1 }}>
          <Space>
            <Text strong style={{ fontSize: 14 }}>
              {path.title}
            </Text>
            <Tag color={riskColor} style={{ fontSize: 11, margin: 0 }}>
              风险 {path.risk_level} ({riskLabel})
            </Tag>
          </Space>
          <Paragraph type="secondary" style={{ fontSize: 12, margin: 0, marginTop: 4 }}>
            {path.description}
          </Paragraph>
        </Space>

        <Space style={{ marginLeft: 12, flexShrink: 0 }}>
          <Button
            size="small"
            icon={editingJson !== null ? <CloseOutlined /> : <EditOutlined />}
            onClick={handleEditToggle}
          >
            {editingJson !== null ? '取消编辑' : '编辑步骤'}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={() => (editingJson !== null ? handleSaveEdited() : onSave())}
          >
            保存为用例
          </Button>
        </Space>
      </div>

      {/* Tags */}
      {path.tags.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {path.tags.map((tag) => (
            <Tag key={tag} style={{ fontSize: 11, marginRight: 4 }}>
              {tag}
            </Tag>
          ))}
        </div>
      )}

      {/* Steps summary (shown when not editing) */}
      {editingJson === null && (
        <>
          <Text type="secondary" style={{ fontSize: 11 }}>
            步骤: {stepSummary}
            {path.steps.length > 5 ? ` ... (+${path.steps.length - 5})` : ''}
          </Text>

          <Collapse
            ghost
            size="small"
            style={{ marginTop: 4 }}
            items={[
              {
                key: 'steps',
                label: <Text style={{ fontSize: 12 }}>查看完整步骤</Text>,
                children: (
                  <pre
                    style={{
                      background: '#1e1e1e',
                      color: '#d4d4d4',
                      padding: 10,
                      borderRadius: 4,
                      fontSize: 11,
                      maxHeight: 240,
                      overflow: 'auto',
                      margin: 0,
                    }}
                  >
                    {JSON.stringify(path.steps, null, 2)}
                  </pre>
                ),
              },
            ]}
          />
        </>
      )}

      {/* Inline JSON editor (shown when editing) */}
      {editingJson !== null && (
        <div style={{ marginTop: 8 }}>
          {jsonError && (
            <Alert type="error" message={jsonError} style={{ marginBottom: 8 }} showIcon />
          )}
          <Input.TextArea
            value={editingJson}
            onChange={(e) => {
              setEditingJson(e.target.value);
              setJsonError(null);
            }}
            rows={10}
            style={{
              fontFamily: 'monospace',
              fontSize: 12,
              background: '#1e1e1e',
              color: '#d4d4d4',
              borderColor: '#444',
            }}
          />
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
            编辑完成后点击「保存为用例」，保存后可在编辑器中继续精调
          </Text>
        </div>
      )}
    </Card>
  );
}
