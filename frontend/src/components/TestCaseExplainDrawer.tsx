import { useState } from 'react';
import {
  Drawer,
  Button,
  Card,
  Tag,
  Spin,
  Skeleton,
  Space,
  Typography,
  Tooltip,
  Alert,
} from 'antd';
import {
  EyeOutlined,
  ReloadOutlined,
  EditOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import type { TestCaseExplainOut, StepExplanation } from '../types';
import * as explainApi from '../api/explain';

const { Text, Title } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: number;
  caseId: number;
  caseName: string;
  onNavigateToStep?: (stepIndex: number) => void;
}

const RISK_COLORS: Record<string, string> = {
  low: '#52c41a',
  medium: '#faad14',
  high: '#ff4d4f',
};

const RISK_LABELS: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

export default function TestCaseExplainDrawer({
  open,
  onClose,
  projectId,
  caseId,
  caseName,
  onNavigateToStep,
}: Props) {
  const [data, setData] = useState<TestCaseExplainOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchExplain = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await explainApi.explainTestCase(projectId, caseId);
      setData(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || '请求失败');
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    if (!data && !loading) {
      fetchExplain();
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <EyeOutlined />
          <span>AI 预演</span>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {caseName}
          </Text>
        </Space>
      }
      width={480}
      open={open}
      onClose={onClose}
      afterOpenChange={(visible) => visible && handleOpen()}
      footer={
        <div style={{ textAlign: 'center' }}>
          <Button icon={<ReloadOutlined />} onClick={fetchExplain} loading={loading}>
            重新预演
          </Button>
        </div>
      }
    >
      {loading && !data && (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <Skeleton active paragraph={{ rows: 2 }} />
          <Skeleton active paragraph={{ rows: 4 }} />
          <Skeleton active paragraph={{ rows: 4 }} />
        </Space>
      )}

      {error && (
        <Alert
          type="error"
          showIcon
          message="预演失败"
          description={error}
          action={
            <Button size="small" danger onClick={fetchExplain}>
              重试
            </Button>
          }
        />
      )}

      {data && (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* Overall Assessment */}
          <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <Text strong>整体风险:</Text>
              <Tag
                color={RISK_COLORS[data.overall_risk] || '#52c41a'}
                style={{ fontSize: 13, padding: '2px 8px' }}
              >
                {RISK_LABELS[data.overall_risk] || '低'}
              </Tag>
            </div>
            {data.overall_advice && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <BulbOutlined style={{ color: '#faad14', marginTop: 3 }} />
                <Text style={{ fontSize: 13 }}>{data.overall_advice}</Text>
              </div>
            )}
          </Card>

          {/* Step Cards */}
          {data.steps.map((step) => (
            <StepCard
              key={step.step_index}
              step={step}
              onNavigate={() => onNavigateToStep?.(step.step_index)}
            />
          ))}
        </Space>
      )}
    </Drawer>
  );
}

function StepCard({
  step,
  onNavigate,
}: {
  step: StepExplanation;
  onNavigate?: () => void;
}) {
  const riskColor = RISK_COLORS[step.risk_level] || '#52c41a';
  const isHighRisk = step.risk_level === 'high';

  return (
    <Card
      size="small"
      style={{
        borderLeft: `4px solid ${riskColor}`,
        borderRadius: 6,
      }}
      bodyStyle={{ padding: '12px 16px' }}
    >
      {/* Header: index + action + confidence */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <Space>
          <Text strong style={{ fontSize: 14 }}>
            #{step.step_index} {step.action}
          </Text>
          <Tooltip title={`置信度 ${(step.confidence * 100).toFixed(0)}%`}>
            <Tag color={riskColor} style={{ fontSize: 11, margin: 0 }}>
              {(step.confidence * 100).toFixed(0)}%
            </Tag>
          </Tooltip>
        </Space>
        {isHighRisk && onNavigate && (
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={onNavigate}
            style={{ padding: 0 }}
          >
            编辑
          </Button>
        )}
      </div>

      {/* Intent */}
      <div style={{ marginBottom: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          意图:
        </Text>
        <Text style={{ fontSize: 13, marginLeft: 4 }}>{step.intent}</Text>
      </div>

      {/* Prediction */}
      <div style={{ marginBottom: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          预期:
        </Text>
        <Text style={{ fontSize: 13, marginLeft: 4 }}>{step.prediction}</Text>
      </div>

      {/* Risk */}
      {step.risk && step.risk !== '无显著风险' && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
          <Text type="secondary" style={{ fontSize: 12, flexShrink: 0 }}>
            风险:
          </Text>
          <Text type="warning" style={{ fontSize: 12 }}>
            {step.risk}
          </Text>
        </div>
      )}
    </Card>
  );
}
