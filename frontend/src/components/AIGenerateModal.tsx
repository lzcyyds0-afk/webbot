import { useState, useEffect } from 'react';
import {
  Modal,
  Form,
  Input,
  Alert,
  Spin,
  Typography,
  Space,
  Tag,
  Switch,
  Button,
  Card,
  Collapse,
  Divider,
  Popconfirm,
} from 'antd';
import {
  RobotOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  CheckOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import CookieExtractor from './CookieExtractor';
import { useLLMStore } from '../stores/llmStore';
import {
  generateSteps,
  refineSteps,
  type GenerateRequest,
  type GenerateResponse,
} from '../api/testCases';
import type { StepDef } from '../types';

const { Text } = Typography;

interface Props {
  open: boolean;
  projectId: number;
  baseUrl: string;
  onClose: (steps: StepDef[] | null) => void;
}

const ACTION_COLORS: Record<string, string> = {
  goto: '#1677ff',
  click: '#52c41a',
  input: '#faad14',
  wait: '#8c8c8c',
  screenshot: '#722ed1',
  drag: '#13c2c2',
  connect: '#eb2f96',
};

export default function AIGenerateModal({ open, projectId, baseUrl, onClose }: Props) {
  const { configs, fetchConfigs } = useLLMStore();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingSteps, setEditingSteps] = useState<StepDef[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<StepDef>({ action: 'click' });
  const [refineFeedback, setRefineFeedback] = useState('');
  const [refining, setRefining] = useState(false);

  useEffect(() => {
    if (open) {
      fetchConfigs();
      setResult(null);
      setError(null);
      setEditingSteps([]);
      setEditingIndex(null);
      setRefineFeedback('');
    }
  }, [open]);

  const defaultLlmId = configs.find((c) => c.is_default)?.id;

  const handleGenerate = async () => {
    try {
      const values = await form.validateFields();
      if (!defaultLlmId) {
        setError('没有默认 LLM 配置，请先在设置中配置并设置默认模型');
        return;
      }
      setLoading(true);
      setError(null);
      setResult(null);

      const req: GenerateRequest = {
        project_id: projectId,
        url: values.url,
        goal: values.goal,
        llm_config_id: defaultLlmId,
        cookies: values.cookies_json ? JSON.parse(values.cookies_json) : undefined,
        thorough: values.thorough ?? false,
      };

      const resp = await generateSteps(req);
      setResult(resp);
      setEditingSteps(resp.steps);
    } catch (e: any) {
      if (e?.errorFields) return;
      setError(e?.response?.data?.detail || e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleRefine = async () => {
    if (!refineFeedback.trim() || editingSteps.length === 0 || !defaultLlmId) return;
    setRefining(true);
    try {
      const resp = await refineSteps({
        steps: editingSteps,
        user_feedback: refineFeedback,
        llm_config_id: defaultLlmId,
      });
      setEditingSteps(resp.steps);
      setRefineFeedback('');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || '优化失败');
    } finally {
      setRefining(false);
    }
  };

  const handleApply = () => {
    if (editingSteps.length > 0) {
      onClose(editingSteps);
    }
  };

  const handleCancel = () => {
    onClose(null);
  };

  const handleDeleteStep = (index: number) => {
    setEditingSteps((prev) => prev.filter((_, i) => i !== index));
    if (editingIndex === index) {
      setEditingIndex(null);
    }
  };

  const handleStartEdit = (index: number) => {
    setEditingIndex(index);
    setEditForm({ ...editingSteps[index] });
  };

  const handleSaveEdit = () => {
    if (editingIndex === null) return;
    setEditingSteps((prev) => {
      const next = [...prev];
      next[editingIndex] = { ...editForm };
      return next;
    });
    setEditingIndex(null);
  };

  const handleAddStep = () => {
    const newStep: StepDef = { action: 'wait', ms: 1000 };
    setEditingSteps((prev) => [...prev, newStep]);
    setEditingIndex(editingSteps.length);
    setEditForm(newStep);
  };

  const handleMoveStep = (index: number, direction: 'up' | 'down') => {
    if (direction === 'up' && index === 0) return;
    if (direction === 'down' && index === editingSteps.length - 1) return;
    setEditingSteps((prev) => {
      const next = [...prev];
      const targetIndex = direction === 'up' ? index - 1 : index + 1;
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
  };

  return (
    <Modal
      title={
        <Space>
          <RobotOutlined />
          <span>AI 生成测试步骤</span>
        </Space>
      }
      open={open}
      onCancel={handleCancel}
      width={720}
      footer={
        editingSteps.length > 0
          ? [
              <Button key="cancel" onClick={handleCancel}>取消</Button>,
              <Button key="apply" type="primary" onClick={handleApply}>
                应用到编辑器
              </Button>,
            ]
          : [
              <Button key="cancel" onClick={handleCancel}>取消</Button>,
              <Button key="generate" type="primary" onClick={handleGenerate} loading={loading}>
                {loading ? '生成中...' : '生成'}
              </Button>,
            ]
      }
      destroyOnClose
    >
      {/* Input form */}
      {editingSteps.length === 0 && (
        <Form form={form} layout="vertical" initialValues={{ url: baseUrl }}>
          <Form.Item
            name="url"
            label="页面 URL"
            rules={[{ required: true, message: '请输入 URL' }, { type: 'url', message: '请输入合法 URL' }]}
          >
            <Input placeholder="https://app.example.com/page" />
          </Form.Item>

          <Form.Item
            name="goal"
            label="目标描述"
            rules={[{ required: true, message: '请描述你想自动化的操作' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="例如：新建一个对话 agent，拖入一个 LLM 节点并连上开始节点"
            />
          </Form.Item>

          <Form.Item name="thorough" valuePropName="checked" initialValue={false}>
            <Switch checkedChildren="全面探索" unCheckedChildren="精简模式" />
          </Form.Item>

          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) =>
              getFieldValue('thorough') ? (
                <Alert
                  type="info"
                  message="全面探索模式"
                  description="AI 会尽可能多地覆盖页面上的按钮、输入框等交互元素，生成更全面的测试步骤。"
                  style={{ marginBottom: 16 }}
                  showIcon
                />
              ) : null
            }
          </Form.Item>

          <Form.Item
            name="cookies_json"
            label={
              <Space>
                <span>Cookies (JSON, 可选)</span>
                <CookieExtractor />
              </Space>
            }
            tooltip="页面需要登录时，传入浏览器 cookies"
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
              rows={2}
              placeholder='[{"name":"session", "value":"xxx", "domain":".example.com"}]'
            />
          </Form.Item>
        </Form>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">正在打开页面、截图、调用 Vision LLM 生成步骤...</Text>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <Alert type="error" message="生成失败" description={error} style={{ marginBottom: 16 }} showIcon />
      )}

      {/* Step Editor */}
      {editingSteps.length > 0 && (
        <div>
          {result && (
            <Alert
              type="success"
              message={`成功生成 ${result.steps.length} 个步骤${result.retry_used ? '（经过一次修正）' : ''}`}
              style={{ marginBottom: 12 }}
              showIcon
            />
          )}

          {/* Refine toolbar */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <Input.TextArea
              value={refineFeedback}
              onChange={(e) => setRefineFeedback(e.target.value)}
              placeholder="输入修改建议，例如：第3步之前加一个等待 / 把selector改成#submit"
              rows={1}
              style={{ flex: 1 }}
            />
            <Button icon={<BulbOutlined />} onClick={handleRefine} loading={refining}>
              优化
            </Button>
            <Button icon={<PlusOutlined />} onClick={handleAddStep}>
              添加
            </Button>
          </div>

          {/* Step list */}
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            {editingSteps.map((step, idx) => (
              <StepCard
                key={idx}
                index={idx}
                step={step}
                isEditing={editingIndex === idx}
                editForm={editForm}
                onStartEdit={() => handleStartEdit(idx)}
                onSaveEdit={handleSaveEdit}
                onCancelEdit={() => setEditingIndex(null)}
                onDelete={() => handleDeleteStep(idx)}
                onMoveUp={() => handleMoveStep(idx, 'up')}
                onMoveDown={() => handleMoveStep(idx, 'down')}
                onUpdateEditForm={setEditForm}
              />
            ))}
          </Space>
        </div>
      )}
    </Modal>
  );
}

// ── Step Card ──

function StepCard({
  index,
  step,
  isEditing,
  editForm,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onDelete,
  onMoveUp,
  onMoveDown,
  onUpdateEditForm,
}: {
  index: number;
  step: StepDef;
  isEditing: boolean;
  editForm: StepDef;
  onStartEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onUpdateEditForm: (s: StepDef) => void;
}) {
  const action = step.action || '?';
  const color = ACTION_COLORS[action] || '#8c8c8c';

  const paramSummary = Object.entries(step)
    .filter(([k]) => k !== 'action')
    .map(([k, v]) => {
      const val = String(v);
      return `${k}=${val.length > 30 ? val.slice(0, 30) + '...' : val}`;
    })
    .join(' | ');

  if (isEditing) {
    return (
      <Card size="small" style={{ borderLeft: `3px solid ${color}` }} bodyStyle={{ padding: 8 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Space>
            <Text strong>#{index}</Text>
            <Tag color={color}>{editForm.action}</Tag>
          </Space>
          <Input
            value={editForm.action}
            onChange={(e) => onUpdateEditForm({ ...editForm, action: e.target.value })}
            placeholder="action"
            style={{ width: 120 }}
          />
          {Object.entries(editForm)
            .filter(([k]) => k !== 'action')
            .map(([k, v]) => (
              <Space key={k}>
                <Input
                  value={k}
                  onChange={(e) => {
                    const newForm = { ...editForm };
                    delete (newForm as any)[k];
                    (newForm as any)[e.target.value] = v;
                    onUpdateEditForm(newForm);
                  }}
                  style={{ width: 100 }}
                />
                <Input
                  value={String(v)}
                  onChange={(e) => onUpdateEditForm({ ...editForm, [k]: e.target.value })}
                  style={{ width: 280 }}
                />
                <Button
                  size="small"
                  danger
                  onClick={() => {
                    const newForm = { ...editForm };
                    delete (newForm as any)[k];
                    onUpdateEditForm(newForm);
                  }}
                >
                  删除
                </Button>
              </Space>
            ))}
          <Space>
            <Button size="small" onClick={() => onUpdateEditForm({ ...editForm, newParam: '' })}>
              + 参数
            </Button>
            <Button size="small" type="primary" icon={<CheckOutlined />} onClick={onSaveEdit}>
              保存
            </Button>
            <Button size="small" onClick={onCancelEdit}>取消</Button>
          </Space>
        </Space>
      </Card>
    );
  }

  return (
    <Card
      size="small"
      style={{ borderLeft: `3px solid ${color}` }}
      bodyStyle={{ padding: '8px 12px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Text strong style={{ fontSize: 13 }}>#{index}</Text>
          <Tag color={color} style={{ margin: 0 }}>{action}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{paramSummary || '—'}</Text>
        </Space>
        <Space>
          <Button size="small" onClick={onMoveUp} disabled={index === 0}>↑</Button>
          <Button size="small" onClick={onMoveDown}>↓</Button>
          <Button size="small" icon={<EyeOutlined />} onClick={onStartEdit}>编辑</Button>
          <Popconfirm title="删除此步骤？" onConfirm={onDelete}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      </div>
    </Card>
  );
}
