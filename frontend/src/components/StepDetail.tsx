import { useState, useEffect } from 'react';
import { Descriptions, Tag, Typography, Tabs, Alert, Spin, Table, Empty, Button } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExpandOutlined,
  MedicineBoxOutlined,
} from '@ant-design/icons';
import { useRunsStore } from '../stores/runsStore';
import StepDiagnosisDrawer from './StepDiagnosisDrawer';
import type { RunStep, StepDetails } from '../types';

const { Text, Paragraph } = Typography;

interface Props {
  step: RunStep;
  runId: number;
  testCaseId: number;
  projectId: number;
}

export default function StepDetail({ step, runId, testCaseId, projectId }: Props) {
  const [activeTab, setActiveTab] = useState('screenshots');
  const [previewImg, setPreviewImg] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const stepDetails = useRunsStore((s) => s.stepDetails[`${runId}-${step.step_index}`]);
  const stepDetailsLoading = useRunsStore((s) => s.stepDetailsLoading[`${runId}-${step.step_index}`]);
  const fetchStepDetails = useRunsStore((s) => s.fetchStepDetails);

  // Auto-fetch details when tab switches to one that needs them
  useEffect(() => {
    if (!stepDetails && !stepDetailsLoading) {
      fetchStepDetails(runId, step.step_index);
    }
  }, [runId, step.step_index, stepDetails, stepDetailsLoading, fetchStepDetails]);

  // Screenshot URLs
  const beforeUrl = `/screenshots/${runId}/${step.step_index}.png`;
  const afterUrl = step.screenshot_path
    ? (step.screenshot_path.startsWith('/') ? step.screenshot_path : `/${step.screenshot_path}`)
    : `/screenshots/${runId}/${step.step_index}_after.png`;

  const statusColor = step.status === 'passed' ? 'success' : step.status === 'failed' ? 'error' : 'processing';

  const details: StepDetails | undefined = stepDetails;

  // ── Console logs table columns ──
  const consoleColumns = [
    {
      title: '级别',
      dataIndex: 'type',
      width: 80,
      render: (v: string) => (
        <Tag color={v === 'error' ? 'error' : v === 'warning' ? 'warning' : 'default'}>{v}</Tag>
      ),
    },
    {
      title: '消息',
      dataIndex: 'text',
      ellipsis: true,
    },
  ];

  // ── Network requests table columns ──
  const networkColumns = [
    {
      title: '方法',
      dataIndex: 'method',
      width: 70,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'response',
      width: 80,
      render: (resp: any) =>
        resp ? (
          <Tag color={resp.status >= 400 ? 'error' : resp.status >= 300 ? 'warning' : 'success'}>
            {resp.status}
          </Tag>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    {
      title: 'URL',
      dataIndex: 'url',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'resource_type',
      width: 90,
    },
  ];

  const tabItems = [
    {
      key: 'screenshots',
      label: '截图对比',
      children: (
        <div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {/* Before */}
            <div style={{ flex: 1, minWidth: 280 }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                执行前
              </Text>
              <div style={{ position: 'relative', cursor: 'zoom-in' }} onClick={() => setPreviewImg(beforeUrl)}>
                <img
                  src={beforeUrl}
                  alt="before"
                  style={{ width: '100%', border: '1px solid #d9d9d9', borderRadius: 4, display: 'block' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
                <ExpandOutlined style={{ position: 'absolute', top: 8, right: 8, color: '#fff', background: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 4 }} />
              </div>
            </div>
            {/* After */}
            <div style={{ flex: 1, minWidth: 280 }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                执行后
              </Text>
              <div style={{ position: 'relative', cursor: 'zoom-in' }} onClick={() => setPreviewImg(afterUrl)}>
                <img
                  src={afterUrl}
                  alt="after"
                  style={{ width: '100%', border: '1px solid #d9d9d9', borderRadius: 4, display: 'block' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
                <ExpandOutlined style={{ position: 'absolute', top: 8, right: 8, color: '#fff', background: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 4 }} />
              </div>
            </div>
          </div>

          {/* BBox overlay info */}
          {details?.target_bbox && (
            <div style={{ marginTop: 12, padding: 12, background: '#f5f5f5', borderRadius: 6 }}>
              <Text strong style={{ display: 'block', marginBottom: 4 }}>目标元素位置</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                x={details.target_bbox.x}, y={details.target_bbox.y},
                width={details.target_bbox.width}, height={details.target_bbox.height}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'dom',
      label: 'DOM 片段',
      children: (
        <div>
          {details?.dom_snippet ? (
            <div>
              <pre
                style={{
                  background: '#1e1e1e',
                  color: '#d4d4d4',
                  padding: 12,
                  borderRadius: 6,
                  fontSize: 12,
                  maxHeight: 400,
                  overflow: 'auto',
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {details.dom_snippet}
              </pre>
            </div>
          ) : (
            <Empty description="无 DOM 片段" />
          )}
        </div>
      ),
    },
    {
      key: 'console',
      label: `控制台日志 ${details?.console_logs ? `(${details.console_logs.length})` : ''}`,
      children: (
        <div>
          {stepDetailsLoading ? (
            <Spin size="small" style={{ display: 'block', margin: '20px auto' }} />
          ) : details?.console_logs && details.console_logs.length > 0 ? (
            <Table
              dataSource={details.console_logs.map((log, i) => ({ ...log, key: i }))}
              columns={consoleColumns}
              size="small"
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              scroll={{ y: 350 }}
            />
          ) : (
            <Empty description="无控制台日志" />
          )}
        </div>
      ),
    },
    {
      key: 'network',
      label: `网络请求 ${details?.network_requests ? `(${details.network_requests.length})` : ''}`,
      children: (
        <div>
          {stepDetailsLoading ? (
            <Spin size="small" style={{ display: 'block', margin: '20px auto' }} />
          ) : details?.network_requests && details.network_requests.length > 0 ? (
            <Table
              dataSource={details.network_requests.map((req, i) => ({ ...req, key: i }))}
              columns={networkColumns}
              size="small"
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              scroll={{ y: 350 }}
              expandable={{
                expandedRowRender: (record: any) => (
                  <div style={{ padding: 8 }}>
                    <Text strong>请求头</Text>
                    <pre style={{ fontSize: 11, marginTop: 4 }}>{JSON.stringify(record.headers, null, 2)}</pre>
                    {record.response && (
                      <>
                        <Text strong style={{ display: 'block', marginTop: 8 }}>响应</Text>
                        <pre style={{ fontSize: 11, marginTop: 4 }}>{JSON.stringify(record.response, null, 2)}</pre>
                      </>
                    )}
                  </div>
                ),
              }}
            />
          ) : (
            <Empty description="无网络请求" />
          )}
        </div>
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      {/* Meta info */}
      <Descriptions
        bordered
        size="small"
        column={2}
        style={{ marginBottom: 16 }}
      >
        <Descriptions.Item label="步骤"># {step.step_index}</Descriptions.Item>
        <Descriptions.Item label="动作">
          <Tag color="blue">{step.action}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusColor} icon={
            step.status === 'passed' ? <CheckCircleOutlined /> :
            step.status === 'failed' ? <CloseCircleOutlined /> : undefined
          }>
            {step.status}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="耗时">
          {step.duration_ms != null ? `${step.duration_ms}ms` : '-'}
        </Descriptions.Item>
      </Descriptions>

      {/* Error alert */}
      {step.error && (
        <Alert
          type="error"
          message="步骤失败"
          description={step.error}
          style={{ marginBottom: 16 }}
          showIcon
          action={
            <Button
              size="small"
              type="primary"
              danger
              icon={<MedicineBoxOutlined />}
              onClick={() => setDrawerOpen(true)}
            >
              诊断
            </Button>
          }
        />
      )}

      {/* Input / Output JSON */}
      <div style={{ marginBottom: 16 }}>
        <Tabs
          defaultActiveKey="input"
          size="small"
          items={[
            {
              key: 'input',
              label: '输入',
              children: (
                <pre style={{
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 6,
                  fontSize: 12,
                  maxHeight: 200,
                  overflow: 'auto',
                  margin: 0,
                }}>
                  {step.input_json ? JSON.stringify(step.input_json, null, 2) : '-'}
                </pre>
              ),
            },
            {
              key: 'output',
              label: '输出',
              children: (
                <pre style={{
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 6,
                  fontSize: 12,
                  maxHeight: 200,
                  overflow: 'auto',
                  margin: 0,
                }}>
                  {step.output_json ? JSON.stringify(step.output_json, null, 2) : '-'}
                </pre>
              ),
            },
            {
              key: 'vlm',
              label: 'VLM 分析',
              children: (() => {
                const vlm = step.output_json?.vlm as Record<string, any> | undefined;
                if (!vlm) return <Text type="secondary">无 VLM 分析结果</Text>;
                return (
                  <div>
                    <Tag color={vlm.passed ? 'success' : 'error'} icon={vlm.passed ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
                      {vlm.passed ? '通过' : '未通过'}
                    </Tag>
                    {vlm.reason && <Paragraph style={{ marginTop: 8 }}>{vlm.reason}</Paragraph>}
                  </div>
                );
              })(),
            },
          ]}
        />
      </div>

      {/* Main detail tabs */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />

      {/* Image preview modal (simple overlay) */}
      {previewImg && (
        <div
          onClick={() => setPreviewImg(null)}
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.85)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 40,
            cursor: 'zoom-out',
          }}
        >
          <img
            src={previewImg}
            alt="preview"
            style={{ maxWidth: '100%', maxHeight: '100%', borderRadius: 4 }}
          />
        </div>
      )}

      {/* Diagnosis drawer */}
      <StepDiagnosisDrawer
        runId={runId}
        stepIndex={step.step_index}
        testCaseId={testCaseId}
        projectId={projectId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
