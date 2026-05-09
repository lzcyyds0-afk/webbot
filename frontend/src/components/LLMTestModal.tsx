import { useState } from 'react';
import {
  Modal,
  Input,
  Button,
  Space,
  Typography,
  Tag,
  Descriptions,
  Spin,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useLLMStore } from '../stores/llmStore';
import type { LLMConfig } from '../types';

const { Text, Paragraph } = Typography;

interface Props {
  open: boolean;
  config: LLMConfig | null;
  onClose: () => void;
}

export default function LLMTestModal({ open, config, onClose }: Props) {
  const { testConfig, testResult, testing, clearTestResult } = useLLMStore();

  const [prompt, setPrompt] = useState('你好，请简短回复。');

  const handleTest = async () => {
    if (!config) return;
    await testConfig(config.id, prompt);
  };

  const handleClose = () => {
    clearTestResult();
    onClose();
  };

  return (
    <Modal
      title={config ? `测试 LLM: ${config.name}` : '测试 LLM'}
      open={open}
      onCancel={handleClose}
      footer={null}
      width={560}
      destroyOnClose
    >
      {config && (
        <div>
          <Descriptions size="small" bordered column={1} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Provider">
              <Tag>{config.provider}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Model">
              <Tag>{config.model}</Tag>
            </Descriptions.Item>
          </Descriptions>

          <div style={{ marginBottom: 12 }}>
            <Text strong style={{ display: 'block', marginBottom: 4 }}>测试 Prompt</Text>
            <Input.TextArea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="输入测试提示词"
            />
          </div>

          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={testing}
            onClick={handleTest}
            style={{ marginBottom: 16, width: '100%' }}
          >
            发送测试
          </Button>

          {/* Result */}
          {testResult && (
            <div
              style={{
                background: testResult.success ? '#f6ffed' : '#fff2f0',
                border: `1px solid ${testResult.success ? '#b7eb8f' : '#ffccc7'}`,
                borderRadius: 8,
                padding: 12,
              }}
            >
              <Space style={{ marginBottom: 8 }}>
                {testResult.success ? (
                  <Tag color="success" icon={<CheckCircleOutlined />}>成功</Tag>
                ) : (
                  <Tag color="error" icon={<CloseCircleOutlined />}>失败</Tag>
                )}
                <Tag>{testResult.model}</Tag>
              </Space>

              {testResult.success ? (
                <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                  {testResult.content}
                </Paragraph>
              ) : (
                <Paragraph type="danger" style={{ margin: 0 }}>
                  {testResult.error}
                </Paragraph>
              )}

              {testResult.success && testResult.usage && Object.keys(testResult.usage).length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Token: {JSON.stringify(testResult.usage)}
                  </Text>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}