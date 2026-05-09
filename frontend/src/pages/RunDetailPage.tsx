import { useEffect, useCallback, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Tag, Spin, Layout, Empty, Progress, Alert, Card, Button, Dropdown, message } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  DownOutlined,
  UpOutlined,
  ExportOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { exportRun } from '../api/runs';
import { useRunsStore } from '../stores/runsStore';
import useRunSocket from '../hooks/useRunSocket';
import StepTimeline from '../components/StepTimeline';
import StepDetail from '../components/StepDetail';
import type { WsMessage } from '../types';

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined /> },
  running: { color: 'processing', icon: <SyncOutlined spin /> },
  passed: { color: 'success', icon: <CheckCircleOutlined /> },
  failed: { color: 'error', icon: <CloseCircleOutlined /> },
};

export default function RunDetailPage() {
  const { id } = useParams();
  const runId = Number(id);
  const navigate = useNavigate();

  const currentRun = useRunsStore((s) => s.currentRun);
  const steps = useRunsStore((s) => s.steps);
  const activeStepIndex = useRunsStore((s) => s.activeStepIndex);
  const loading = useRunsStore((s) => s.loading);
  const fetchRun = useRunsStore((s) => s.fetchRun);
  const fetchSteps = useRunsStore((s) => s.fetchSteps);
  const handleWsMessage = useRunsStore((s) => s.handleWsMessage);
  const setActiveStepIndex = useRunsStore((s) => s.setActiveStepIndex);
  const reset = useRunsStore((s) => s.reset);

  // Load run + steps on mount
  useEffect(() => {
    if (!runId) return;
    fetchRun(runId).catch(() => navigate('/projects'));
    fetchSteps(runId);
    return () => reset();
  }, [runId, fetchRun, fetchSteps, reset, navigate]);

  // WebSocket
  const onMessage = useCallback(
    (msg: WsMessage) => handleWsMessage(msg),
    [handleWsMessage],
  );
  useRunSocket({ runId, onMessage });

  const statusInfo = currentRun ? STATUS_CONFIG[currentRun.status] : STATUS_CONFIG.pending;

  // Compute elapsed time
  const elapsed = (() => {
    if (!currentRun?.started_at) return null;
    const start = new Date(currentRun.started_at).getTime();
    const end = currentRun.finished_at ? new Date(currentRun.finished_at).getTime() : Date.now();
    const ms = end - start;
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
  })();

  // Step stats
  const stepStats = useMemo(() => {
    const total = steps.length;
    const passed = steps.filter((s) => s.status === 'passed').length;
    const failed = steps.filter((s) => s.status === 'failed').length;
    const running = steps.filter((s) => s.status === 'running').length;
    const pending = total - passed - failed - running;
    const completed = passed + failed;
    const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

    // ETA estimation
    let eta: string | null = null;
    if (currentRun?.status === 'running' && completed > 0 && total > completed) {
      const avgMs =
        steps
          .filter((s) => s.duration_ms != null)
          .reduce((sum, s) => sum + (s.duration_ms || 0), 0) / completed;
      const remaining = total - completed;
      const etaMs = avgMs * remaining;
      if (etaMs < 60_000) {
        eta = `${Math.round(etaMs / 1000)}s`;
      } else {
        eta = `${Math.floor(etaMs / 60_000)}m ${Math.round((etaMs % 60_000) / 1000)}s`;
      }
    }

    return { total, passed, failed, running, pending, completed, percent, eta };
  }, [steps, currentRun?.status]);

  // Auto-select first step if current index is invalid
  const activeStep = steps.find((s) => s.step_index === activeStepIndex) ?? steps[0] ?? null;

  // Narrative expand state
  const [narrativeExpanded, setNarrativeExpanded] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);

  const narrative = currentRun?.narrative;
  const runFinished = currentRun?.status === 'passed' || currentRun?.status === 'failed';

  const handleExport = async (format: 'html' | 'pdf') => {
    setExportLoading(true);
    try {
      const resp = await exportRun(runId, format);
      window.open(resp.download_url, '_blank');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '导出失败');
    } finally {
      setExportLoading(false);
    }
  };

  if (loading && !currentRun) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
            返回
          </Button>
          <Title level={3} style={{ margin: 0 }}>运行 #{runId}</Title>
          {currentRun && (
            <Tag color={statusInfo.color} icon={statusInfo.icon}>
              {currentRun.status}
            </Tag>
          )}
          {runFinished && (
            <Dropdown
              menu={{
                items: [
                  { key: 'html', label: '导出 HTML', onClick: () => handleExport('html') },
                  { key: 'pdf', label: '导出 PDF', onClick: () => handleExport('pdf') },
                ],
              }}
            >
              <Button icon={<ExportOutlined />} loading={exportLoading} size="small">
                导出报告
              </Button>
            </Dropdown>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {elapsed && (
            <Text type="secondary">耗时: {elapsed}</Text>
          )}
          {stepStats.eta && (
            <Text type="secondary">预计剩余: {stepStats.eta}</Text>
          )}
          <Text type="secondary">
            步骤: {stepStats.total > 0 ? `${stepStats.passed}/${stepStats.total}` : '-'}
          </Text>
        </div>
      </div>

      {/* Narrative Summary */}
      {runFinished && narrative && (
        <Alert
          type={currentRun?.status === 'passed' ? 'success' : 'error'}
          showIcon
          icon={<FileTextOutlined />}
          message={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text strong>{narrative.summary}</Text>
              <Button
                type="link"
                size="small"
                onClick={() => setNarrativeExpanded((v) => !v)}
                icon={narrativeExpanded ? <UpOutlined /> : <DownOutlined />}
              >
                {narrativeExpanded ? '收起' : '展开'}
              </Button>
            </div>
          }
          description={
            narrativeExpanded ? (
              <div style={{ marginTop: 8 }}>
                <Card size="small" style={{ marginBottom: 8, background: 'transparent', border: 'none' }} bodyStyle={{ padding: 0 }}>
                  <Text type="secondary" style={{ fontSize: 13, lineHeight: 1.6 }}>
                    {narrative.process}
                  </Text>
                </Card>
                <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
                  <Text strong style={{ fontSize: 13 }}>结论与建议：</Text>
                  <Text type="secondary" style={{ fontSize: 13, marginLeft: 8 }}>
                    {narrative.conclusion}
                  </Text>
                </div>
              </div>
            ) : null
          }
          style={{ marginBottom: 12 }}
        />
      )}
      {runFinished && !narrative && (
        <Alert
          type="info"
          showIcon
          icon={<SyncOutlined spin />}
          message="AI 报告生成中..."
          style={{ marginBottom: 12 }}
        />
      )}

      {/* Progress bar */}
      {stepStats.total > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Progress
            percent={stepStats.percent}
            status={currentRun?.status === 'failed' ? 'exception' : 'active'}
            strokeColor={currentRun?.status === 'failed' ? '#ff4d4f' : undefined}
            size="small"
            format={(percent) => (
              <span style={{ fontSize: 12 }}>
                {stepStats.completed}/{stepStats.total}
              </span>
            )}
          />
          <div style={{ display: 'flex', gap: 12, marginTop: 4, flexWrap: 'wrap' }}>
            {stepStats.passed > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                <CheckCircleOutlined style={{ color: '#52c41a' }} /> 通过 {stepStats.passed}
              </Text>
            )}
            {stepStats.failed > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> 失败 {stepStats.failed}
              </Text>
            )}
            {stepStats.running > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                <SyncOutlined spin style={{ color: '#1677ff' }} /> 运行中 {stepStats.running}
              </Text>
            )}
            {stepStats.pending > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                <ClockCircleOutlined style={{ color: '#999' }} /> 等待 {stepStats.pending}
              </Text>
            )}
          </div>
        </div>
      )}

      {/* Body */}
      {steps.length === 0 && currentRun?.status === 'pending' ? (
        <Empty description="等待运行开始..." />
      ) : (
        <Layout style={{ flex: 1, background: 'transparent', minHeight: 0 }}>
          <Sider
            width={320}
            style={{
              background: '#fafafa',
              borderRadius: 8,
              marginRight: 12,
              overflow: 'auto',
              height: '100%',
            }}
          >
            <StepTimeline
              steps={steps}
              activeIndex={activeStepIndex}
              onSelect={setActiveStepIndex}
            />
          </Sider>
          <Content
            style={{
              background: '#fff',
              borderRadius: 8,
              overflow: 'auto',
              height: '100%',
              border: '1px solid #f0f0f0',
            }}
          >
            {activeStep ? (
              <StepDetail
                step={activeStep}
                runId={runId}
                testCaseId={currentRun?.test_case_id ?? 0}
                projectId={currentRun?.project_id ?? 0}
              />
            ) : (
              <Empty description="选择一个步骤查看详情" />
            )}
          </Content>
        </Layout>
      )}
    </div>
  );
}
