import { useEffect } from 'react';
import {
  Modal,
  Form,
  Input,
  Select,
  Switch,
} from 'antd';
import { useLLMStore } from '../stores/llmStore';
import type { LLMConfig, LLMProvider } from '../types';

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'ollama', label: 'Ollama' },
];

const PROVIDER_DEFAULT_URL: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  ollama: 'http://localhost:11434',
};

interface Props {
  open: boolean;
  editingConfig: LLMConfig | null;
  onClose: () => void;
}

export default function LLMConfigModal({ open, editingConfig, onClose }: Props) {
  const { createConfig, updateConfig } = useLLMStore();
  const [form] = Form.useForm();
  const isEdit = !!editingConfig;

  // Populate form when editing
  useEffect(() => {
    if (!open) return;
    if (editingConfig) {
      form.setFieldsValue({
        name: editingConfig.name,
        provider: editingConfig.provider,
        model: editingConfig.model,
        api_key: '', // never prefill encrypted key
        base_url: editingConfig.base_url ?? '',
        params_json: editingConfig.params_json
          ? JSON.stringify(editingConfig.params_json, null, 2)
          : '',
        is_default: editingConfig.is_default,
      });
    } else {
      form.resetFields();
    }
  }, [open, editingConfig]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const data = {
        name: values.name,
        provider: values.provider,
        model: values.model,
        api_key: values.api_key,
        base_url: values.base_url || undefined,
        params_json: values.params_json ? JSON.parse(values.params_json) : undefined,
        is_default: values.is_default ?? false,
      };

      if (isEdit) {
        const updateData: Record<string, any> = {};
        // Only send api_key if user entered a new one
        if (values.api_key) updateData.api_key = values.api_key;
        updateData.name = data.name;
        updateData.provider = data.provider;
        updateData.model = data.model;
        updateData.base_url = data.base_url;
        updateData.params_json = data.params_json;
        updateData.is_default = data.is_default;
        await updateConfig(editingConfig!.id, updateData);
      } else {
        await createConfig(data);
      }
      onClose();
    } catch {
      // validation error
    }
  };

  const handleProviderChange = (provider: LLMProvider) => {
    const baseUrlField = form.getFieldValue('base_url');
    // Auto-fill base_url if empty or matches another provider's default
    if (!baseUrlField || Object.values(PROVIDER_DEFAULT_URL).includes(baseUrlField)) {
      form.setFieldValue('base_url', PROVIDER_DEFAULT_URL[provider] ?? '');
    }
  };

  return (
    <Modal
      title={isEdit ? '编辑 LLM 配置' : '新增 LLM 配置'}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      okText={isEdit ? '保存' : '创建'}
      cancelText="取消"
      width={560}
      destroyOnClose
    >
      <Form form={form} layout="vertical" autoComplete="off">
        <Form.Item
          name="name"
          label="名称"
          rules={[{ required: true, message: '请输入配置名称' }]}
        >
          <Input placeholder="例如：GPT-4o" />
        </Form.Item>

        <Form.Item
          name="provider"
          label="Provider"
          rules={[{ required: true, message: '请选择 Provider' }]}
        >
          <Select
            options={PROVIDER_OPTIONS}
            placeholder="选择 Provider"
            onChange={handleProviderChange}
          />
        </Form.Item>

        <Form.Item
          name="model"
          label="Model"
          rules={[{ required: true, message: '请输入模型名称' }]}
        >
          <Input placeholder="例如：gpt-4o / claude-sonnet-4-20250514" />
        </Form.Item>

        <Form.Item
          name="api_key"
          label="API Key"
          rules={isEdit ? [] : [{ required: true, message: '请输入 API Key' }]}
          extra={isEdit ? '留空则不修改' : undefined}
        >
          <Input.Password placeholder={isEdit ? '留空不修改' : 'sk-...'} />
        </Form.Item>

        <Form.Item name="base_url" label="Base URL">
          <Input placeholder="留空使用默认" />
        </Form.Item>

        <Form.Item
          name="params_json"
          label="额外参数 (JSON)"
          rules={[
            {
              validator: (_, value) => {
                if (!value) return Promise.resolve();
                try {
                  JSON.parse(value);
                  return Promise.resolve();
                } catch {
                  return Promise.reject('必须是合法 JSON');
                }
              },
            },
          ]}
        >
          <Input.TextArea rows={3} placeholder='{"temperature": 0.7}' />
        </Form.Item>

        <Form.Item name="is_default" label="设为默认" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}