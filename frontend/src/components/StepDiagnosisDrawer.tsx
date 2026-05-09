import { useEffect, useState } from 'react';
import {
  Drawer,
  Tag,
  Typography,
  Button,
  Space,
  Table,
  Empty,
  Spin,
  Alert,
  Divider,
  message,
} from 'antd';
import {
  CopyOutlined,
  FileSearchOutlined,
  RobotOutlined,
  ExpandOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  VerticalAlignBottomOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useRunsStore } from '../stores/runsStore';
import AiFixReviewModal from './AiFixReviewModal';
import type { StepDiagnosis, CandidateSelector, StepDef } from '../types';
import * as testCasesApi from '../api/testCases';

const { Title, Text, Paragraph } = Typography;

interface Props {
  runId: number;
  stepIndex: number;
  testCaseId: number;
  projectId: number;
  open: boolean;
  onClose: () => void;
}

export default function StepDiagnosisDrawer({ runId, stepIndex, testCaseId, projectId, open, onClose }: Props) {
  const [previewImg, setPreviewImg] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [originalSteps, setOriginalSteps] = useState<StepDef[]>([]);
  const [testCaseLoading, setTestCaseLoading] = useState(false);

  const diagnosis = useRunsStore((s) => s.stepDiagnoses[`${runId}-${stepIndex}`]);
  const loading = useRunsStore((s) => s.stepDiagnosesLoading[`${runId}-${stepIndex}`]);
  const fetchStepDiagnosis = useRunsStore((s) => s.fetchStepDiagnosis);
  const runAiDiagnosis = useRunsStore((s) => s.runAiDiagnosis);

  // Fetch test case steps when drawer opens
  useEffect(() => {
    if (open && testCaseId && projectId) {
      setTestCaseLoading(true);
      testCasesApi.fetchTestCase(projectId, testCaseId)
        .then((tc) => setOriginalSteps(tc.steps_json))
        .catch(() => setOriginalSteps([]))
        .finally(() => setTestCaseLoading(false));
    }
  }, [open, testCaseId, projectId]);

  useEffect(() => {
    if (open && !diagnosis && !loading) {
      fetchStepDiagnosis(runId, stepIndex);
    }
  }, [open, runId, stepIndex, diagnosis, loading, fetchStepDiagnosis]);

  const payload = diagnosis?.payload_json;
  const aiDiagnosis = payload?.ai_diagnosis;

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
      .then(() => message.success('已复制到剪贴板'))
      .catch(() => message.error('复制失败'));
  };

  const errorTypeColor: Record<string, string> = {
    TimeoutError: 'orange',
    SelectorError: 'volcano',
    NavigationError: 'geekblue',
    VisibilityError: 'purple',
    StaleElementError: 'magenta',
    ExecutionError: 'red',
    UnknownError: 'default',
  };

  const rootCauseColor: Record<string, string> = {
    element_not_found: 'error',
    element_occluded: 'warning',
    wait_needed: 'processing',
    network_pending: 'blue',
    auth_expired: 'purple',
    selector_changed: 'volcano',
    other: 'default',
  };

  const fixTypeColor: Record<string, string> = {
    update_selector: 'success',
    add_wait: 'processing',
    add_scroll: 'cyan',
    login_first: 'purple',
    change_text: 'blue',
    remove_step: 'default',
    other: 'default',
  };

  // ── DOM state tags ──
  const renderDomState = (ctx: StepDiagnosis['payload_json']['context']) => (
    <Space wrap>
      <Tag color={ctx.dom_exists ? 'success' : 'error'} icon={ctx.dom_exists ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
        DOM {ctx.dom_exists ? '存在' : '不存在'}
      </Tag>
      <Tag color={ctx.dom_visible ? 'success' : 'warning'} icon={ctx.dom_visible ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}>
        {ctx.dom_visible ? '可见' : '不可见'}
      </Tag>
      <Tag color={ctx.dom_obscured ? 'error' : 'success'} icon={ctx.dom_obscured ? <CloseCircleOutlined /> : <CheckCircleOutlined />}>
        {ctx.dom_obscured ? '被遮挡' : '未被遮挡'}
      </Tag>
    </Space>
  );

  // ── Suggestion tags ──
  const renderSuggestions = (fixes: StepDiagnosis['payload_json']['fixes']) => (
    <Space wrap>
      {fixes.suggest_wait && (
        <Tag color="blue" icon={<ClockCircleOutlined />}>建议等待</Tag>
      )}
      {fixes.suggest_scroll && (
        <Tag color="cyan" icon={<VerticalAlignBottomOutlined />}>建议滚动</Tag>
      )}
      {fixes.suggest_retry && (
        <Tag color="orange" icon={<ReloadOutlined />}>建议重试</Tag>
      )}
      {!fixes.suggest_wait && !fixes.suggest_scroll && !fixes.suggest_retry && (
        <Text type="secondary">无自动建议</Text>
      )}
    </Space>
  );

  // ── Candidate selectors table ──
  const candidateColumns = [
    {
      title: 'Selector',
      dataIndex: 'selector',
      render: (text: string, record: CandidateSelector) => (
        <Space>
          <code style={{ fontSize: 12, background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>{text}</code>
          <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy(text)} />
        </Space>
      ),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 90,
      render: (v: number) => (
        <Tag color={v >= 0.7 ? 'success' : v >= 0.4 ? 'warning' : 'default'}>{Math.round(v * 100)}%</Tag>
      ),
    },
    {
      title: '匹配理由',
      dataIndex: 'reason',
      ellipsis: true,
    },
    {
      title: '匹配数',
      dataIndex: 'found_count',
      width: 80,
    },
  ];

  return (
    <>
      <Drawer
        title={
          <Space>
            <span>步骤诊断</span>
            {payload && (
              <>
                <Tag color="blue">{payload.summary.action}</Tag>
                <Tag color={errorTypeColor[payload.summary.error_type] || 'default'}>
                  {payload.summary.error_type}
                </Tag>
              </>
            )}
          </Space>
        }
        placement="right"
        width={800}
        onClose={onClose}
        open={open}
        styles={{ body: { paddingBottom: 80 } }}
      >
        {loading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : !payload ? (
          <Empty description="暂无诊断数据" style={{ marginTop: 60 }} />
        ) : (
          <div>
            {/* ── 失败摘要 ── */}
            <section style={{ marginBottom: 24 }}>
              <Title level={5}>失败摘要</Title>
              <Alert
                type="error"
                showIcon
                message={payload.summary.error_type}
                description={
                  <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                    {payload.summary.error_text}
                  </Paragraph>
                }
              />
              {payload.summary.selector && (
                <div style={{ marginTop: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>目标 Selector</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                    <code
                      style={{
                        flex: 1,
                        fontSize: 13,
                        background: '#f5f5f5',
                        padding: '6px 10px',
                        borderRadius: 6,
                        wordBreak: 'break-all',
                      }}
                    >
                      {payload.summary.selector}
                    </code>
                    <Button icon={<CopyOutlined />} onClick={() => handleCopy(payload.summary.selector!)}>
                      复制
                    </Button>
                  </div>
                </div>
              )}
            </section>

            <Divider style={{ margin: '16px 0' }} />

            {/* ── 上下文快照 ── */}
            <section style={{ marginBottom: 24 }}>
              <Title level={5}>上下文快照</Title>

              {/* Screenshot */}
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>失败瞬间截图</Text>
                <div
                  style={{ position: 'relative', cursor: 'zoom-in', maxWidth: 480 }}
                  onClick={() => setPreviewImg(payload.context.screenshot_url)}
                >
                  <img
                    src={payload.context.screenshot_url}
                    alt="failure screenshot"
                    style={{ width: '100%', border: '1px solid #d9d9d9', borderRadius: 4, display: 'block' }}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  <ExpandOutlined
                    style={{
                      position: 'absolute',
                      top: 8,
                      right: 8,
                      color: '#fff',
                      background: 'rgba(0,0,0,0.5)',
                      padding: 4,
                      borderRadius: 4,
                    }}
                  />
                </div>
              </div>

              {/* DOM state */}
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>DOM 状态</Text>
                {renderDomState(payload.context)}
              </div>

              {/* Page info */}
              <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 6 }}>
                <div style={{ marginBottom: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>页面 URL: </Text>
                  <Text code style={{ fontSize: 12 }}>{payload.context.page_url}</Text>
                </div>
                <div style={{ marginBottom: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>页面标题: </Text>
                  <Text style={{ fontSize: 12 }}>{payload.context.page_title}</Text>
                </div>
                {payload.context.expected_url && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>预期 URL: </Text>
                    <Text code style={{ fontSize: 12 }}>{payload.context.expected_url}</Text>
                  </div>
                )}
              </div>

              {/* Viewport info */}
              <div style={{ marginTop: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  视口: {payload.context.viewport_info.width} x {payload.context.viewport_info.height}
                  {' | '}滚动: ({payload.context.viewport_info.scroll_x}, {payload.context.viewport_info.scroll_y})
                </Text>
              </div>
            </section>

            <Divider style={{ margin: '16px 0' }} />

            {/* ── 视觉对比 ── */}
            <section style={{ marginBottom: 24 }}>
              <Title level={5}>视觉对比</Title>
              {payload.visual_diff.has_baseline ? (
                <div>
                  <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                    上一次成功运行 #{payload.visual_diff.baseline_run_id}
                    {payload.visual_diff.baseline_run_started_at && (
                      <span> ({new Date(payload.visual_diff.baseline_run_started_at).toLocaleString()})</span>
                    )}
                  </Text>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 280 }}>
                      <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>基线（成功）</Text>
                      <div style={{ position: 'relative', cursor: 'zoom-in' }} onClick={() => setPreviewImg(payload.visual_diff.baseline_screenshot_url!)}>
                        <img
                          src={payload.visual_diff.baseline_screenshot_url!}
                          alt="baseline"
                          style={{ width: '100%', border: '1px solid #d9d9d9', borderRadius: 4, display: 'block' }}
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                        />
                        <ExpandOutlined style={{ position: 'absolute', top: 8, right: 8, color: '#fff', background: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 4 }} />
                      </div>
                    </div>
                    <div style={{ flex: 1, minWidth: 280 }}>
                      <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>本次（失败）</Text>
                      <div style={{ position: 'relative', cursor: 'zoom-in' }} onClick={() => setPreviewImg(payload.visual_diff.current_screenshot_url)}>
                        <img
                          src={payload.visual_diff.current_screenshot_url}
                          alt="current"
                          style={{ width: '100%', border: '1px solid #d9d9d9', borderRadius: 4, display: 'block' }}
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                        />
                        <ExpandOutlined style={{ position: 'absolute', top: 8, right: 8, color: '#fff', background: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 4 }} />
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <Empty description="无基线截图（暂无上一次成功运行）" />
              )}
            </section>

            <Divider style={{ margin: '16px 0' }} />

            {/* ── 建议修复 ── */}
            <section style={{ marginBottom: 24 }}>
              <Title level={5}>建议修复</Title>

              {payload.visual_diff.diff_note && (
                <Alert
                  type="info"
                  showIcon
                  message={payload.visual_diff.diff_note}
                  style={{ marginBottom: 16 }}
                />
              )}

              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>自动建议</Text>
                {renderSuggestions(payload.fixes)}
              </div>

              <div>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>候选 Selector</Text>
                {payload.fixes.candidate_selectors.length > 0 ? (
                  <Table
                    dataSource={payload.fixes.candidate_selectors.map((c, i) => ({ ...c, key: i }))}
                    columns={candidateColumns}
                    size="small"
                    pagination={false}
                  />
                ) : (
                  <Empty description="未找到候选 selector" />
                )}
              </div>
            </section>

            <Divider style={{ margin: '16px 0' }} />

            {/* ── AI 深度诊断 ── */}
            <section style={{ marginBottom: 24 }}>
              <Title level={5}>AI 深度诊断</Title>

              {aiDiagnosis ? (
                <div>
                  {aiDiagnosis.confidence < 0.6 && (
                    <Alert
                      type="warning"
                      showIcon
                      message="低置信度"
                      description="AI 对此次诊断的把握较低，建议人工复核。"
                      style={{ marginBottom: 12 }}
                    />
                  )}

                  <div style={{ marginBottom: 12 }}>
                    <Space wrap>
                      <Tag color={rootCauseColor[aiDiagnosis.root_cause] || 'default'}>
                        {aiDiagnosis.root_cause}
                      </Tag>
                      <Tag color={aiDiagnosis.confidence >= 0.8 ? 'success' : aiDiagnosis.confidence >= 0.6 ? 'warning' : 'error'}>
                        置信度 {Math.round(aiDiagnosis.confidence * 100)}%
                      </Tag>
                      <Tag color={fixTypeColor[aiDiagnosis.suggested_fix?.type] || 'default'}>
                        {aiDiagnosis.suggested_fix?.type}
                      </Tag>
                    </Space>
                  </div>

                  <Alert
                    type="info"
                    showIcon
                    message="AI 分析"
                    description={
                      <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                        {aiDiagnosis.explanation}
                      </Paragraph>
                    }
                    style={{ marginBottom: 16 }}
                  />

                  {aiDiagnosis.suggested_fix?.new_steps_patch && aiDiagnosis.suggested_fix.new_steps_patch.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>
                        建议修改 ({aiDiagnosis.suggested_fix.new_steps_patch.length} 处)
                      </Text>
                      {aiDiagnosis.suggested_fix.new_steps_patch.map((op: any, i: number) => (
                        <div key={i} style={{ marginBottom: 8, padding: 8, background: '#f5f5f5', borderRadius: 4 }}>
                          <Tag color={op.op === 'replace' ? 'blue' : op.op === 'insert' ? 'green' : 'red'}>
                            {op.op}
                          </Tag>
                          <Text style={{ marginLeft: 8 }}>步骤 #{op.step_index}</Text>
                          {op.step && (
                            <pre style={{ margin: '4px 0 0 0', fontSize: 11, background: '#fff', padding: 4, borderRadius: 2 }}>
                              {JSON.stringify(op.step, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}

                      <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        disabled={testCaseLoading || originalSteps.length === 0}
                        onClick={() => setReviewOpen(true)}
                      >
                        应用建议
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <Empty
                  description="尚未进行 AI 诊断"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </section>
          </div>
        )}

        {/* ── Footer actions ── */}
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            padding: '12px 24px',
            borderTop: '1px solid #f0f0f0',
            background: '#fff',
            display: 'flex',
            gap: 12,
            justifyContent: 'flex-end',
          }}
        >
          <Button
            icon={<CopyOutlined />}
            disabled={!payload?.summary.selector}
            onClick={() => handleCopy(payload?.summary.selector || '')}
          >
            复制 Selector
          </Button>
          <Button
            icon={<FileSearchOutlined />}
            disabled={!payload}
            onClick={() => {
              window.open(`/runs/${runId}/trace`, '_blank');
            }}
          >
            打开 Trace
          </Button>
          <Button
            type="primary"
            icon={<RobotOutlined />}
            disabled={!payload || loading}
            loading={loading}
            onClick={() => runAiDiagnosis(runId, stepIndex)}
          >
            让 AI 诊断
          </Button>
        </div>
      </Drawer>

      {/* Image preview overlay */}
      {previewImg && (
        <div
          onClick={() => setPreviewImg(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.85)',
            zIndex: 1100,
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

      {/* AI Fix Review Modal */}
      {aiDiagnosis?.suggested_fix?.new_steps_patch && (
        <AiFixReviewModal
          open={reviewOpen}
          onClose={() => setReviewOpen(false)}
          projectId={projectId}
          testCaseId={testCaseId}
          originalSteps={originalSteps}
          patch={aiDiagnosis.suggested_fix.new_steps_patch}
        />
      )}
    </>
  );
}
