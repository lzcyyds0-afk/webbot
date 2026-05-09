import { useMemo, useState } from 'react';
import { Modal, Button, Space, Typography, Alert, Tag, Spin } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, SaveOutlined } from '@ant-design/icons';
import type { StepDef, PatchOp } from '../types';
import * as testCasesApi from '../api/testCases';

const { Text, Title } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: number;
  testCaseId: number;
  originalSteps: StepDef[];
  patch: PatchOp[];
}

function applyPatch(steps: StepDef[], patch: PatchOp[]): StepDef[] {
  const result = [...steps];
  const sorted = [...patch].sort((a, b) => b.step_index - a.step_index);
  for (const op of sorted) {
    if (op.op === 'replace' && op.step) result[op.step_index] = op.step;
    else if (op.op === 'insert' && op.step) result.splice(op.step_index, 0, op.step);
    else if (op.op === 'delete') result.splice(op.step_index, 1);
  }
  return result;
}

function formatStep(step: StepDef, index: number, highlight?: 'added' | 'removed' | 'changed') {
  const colors: Record<string, string> = {
    added: '#f6ffed',
    removed: '#fff1f0',
    changed: '#e6f7ff',
  };
  const borderColors: Record<string, string> = {
    added: '#b7eb8f',
    removed: '#ffa39e',
    changed: '#91d5ff',
  };
  return (
    <div
      key={index}
      style={{
        padding: '6px 10px',
        marginBottom: 4,
        borderRadius: 4,
        fontSize: 12,
        fontFamily: 'monospace',
        background: highlight ? colors[highlight] : '#fafafa',
        border: `1px solid ${highlight ? borderColors[highlight] : '#f0f0f0'}`,
      }}
    >
      <Text strong style={{ marginRight: 8 }}>#{index}</Text>
      <Tag color="blue">{step.action}</Tag>
      <Text type="secondary" style={{ marginLeft: 8 }}>
        {JSON.stringify(Object.fromEntries(Object.entries(step).filter(([k]) => k !== 'action')))}
      </Text>
    </div>
  );
}

export default function AiFixReviewModal({ open, onClose, projectId, testCaseId, originalSteps, patch }: Props) {
  const [saving, setSaving] = useState(false);

  const patchedSteps = useMemo(() => applyPatch(originalSteps, patch), [originalSteps, patch]);

  const changedIndices = new Set<number>();
  const addedIndices = new Set<number>();
  const removedIndices = new Set<number>();

  for (const op of patch) {
    if (op.op === 'replace') changedIndices.add(op.step_index);
    if (op.op === 'insert') addedIndices.add(op.step_index);
    if (op.op === 'delete') removedIndices.add(op.step_index);
  }

  const maxLen = Math.max(originalSteps.length, patchedSteps.length);

  const handleSave = async () => {
    setSaving(true);
    try {
      await testCasesApi.updateTestCaseSteps(projectId, testCaseId, patchedSteps);
      onClose();
    } catch (err) {
      console.error('Failed to save patched steps:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title="Review AI 修复建议"
      width={900}
      footer={
        <Space>
          <Button onClick={onClose} disabled={saving}>取消</Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={handleSave}
          >
            保存到用例
          </Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        message="以下是用例步骤的变更对比"
        description="左侧为当前步骤，右侧为应用 AI 建议后的步骤。请确认后再保存。"
        style={{ marginBottom: 16 }}
      />

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>
            <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
            当前
          </Title>
          {originalSteps.map((s, i) =>
            formatStep(s, i, removedIndices.has(i) ? 'removed' : undefined)
          )}
        </div>
        <div style={{ flex: 1 }}>
          <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>
            <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
            建议
          </Title>
          {patchedSteps.map((s, i) => {
            const isNew = i >= originalSteps.length || addedIndices.has(i);
            const isChanged = changedIndices.has(i);
            return formatStep(s, i, isNew ? 'added' : isChanged ? 'changed' : undefined);
          })}
        </div>
      </div>

      {saving && (
        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <Spin size="small" tip="保存中..." />
        </div>
      )}
    </Modal>
  );
}
