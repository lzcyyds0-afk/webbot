import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Popconfirm,
  Typography,
  Tag,
  Switch,
  message,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useLLMStore } from '../stores/llmStore';
import LLMConfigModal from '../components/LLMConfigModal';
import LLMTestModal from '../components/LLMTestModal';
import type { LLMConfig } from '../types';

const { Title } = Typography;

const PROVIDER_COLOR: Record<string, string> = {
  openai: 'green',
  anthropic: 'orange',
  gemini: 'blue',
  ollama: 'purple',
};

export default function LLMSettingsPage() {
  const configs = useLLMStore((s) => s.configs);
  const loading = useLLMStore((s) => s.loading);
  const fetchConfigs = useLLMStore((s) => s.fetchConfigs);
  const deleteConfig = useLLMStore((s) => s.deleteConfig);
  const updateConfig = useLLMStore((s) => s.updateConfig);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<LLMConfig | null>(null);
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [testingConfig, setTestingConfig] = useState<LLMConfig | null>(null);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const handleCreate = () => {
    setEditingConfig(null);
    setModalOpen(true);
  };

  const handleEdit = (record: LLMConfig) => {
    setEditingConfig(record);
    setModalOpen(true);
  };

  const handleTest = (record: LLMConfig) => {
    setTestingConfig(record);
    setTestModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    await deleteConfig(id);
    message.success('配置已删除');
  };

  const handleDefaultChange = async (record: LLMConfig, checked: boolean) => {
    await updateConfig(record.id, { is_default: checked });
    message.success(checked ? '已设为默认' : '已取消默认');
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: '名称',
      dataIndex: 'name',
    },
    {
      title: 'Provider',
      dataIndex: 'provider',
      width: 120,
      render: (v: string) => <Tag color={PROVIDER_COLOR[v] ?? 'default'}>{v}</Tag>,
    },
    {
      title: 'Model',
      dataIndex: 'model',
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      ellipsis: true,
      render: (v: string | null) => v ?? <Tag>默认</Tag>,
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 80,
      render: (v: boolean, record: LLMConfig) => (
        <Switch
          size="small"
          checked={v}
          onChange={(checked) => handleDefaultChange(record, checked)}
        />
      ),
    },
    {
      title: '操作',
      width: 220,
      render: (_: unknown, record: LLMConfig) => (
        <Space>
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => handleTest(record)}
          >
            测试
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="删除该配置？"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button size="small" icon={<DeleteOutlined />} danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>LLM 配置</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新增配置
        </Button>
      </div>

      <Table
        rowKey="id"
        dataSource={configs}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      <LLMConfigModal
        open={modalOpen}
        editingConfig={editingConfig}
        onClose={() => { setModalOpen(false); setEditingConfig(null); }}
      />

      <LLMTestModal
        open={testModalOpen}
        config={testingConfig}
        onClose={() => { setTestModalOpen(false); setTestingConfig(null); }}
      />
    </div>
  );
}