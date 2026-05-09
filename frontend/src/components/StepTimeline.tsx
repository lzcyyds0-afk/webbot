import { useRef, useEffect } from 'react';
import { Tag, Typography } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import type { RunStep } from '../types';

const { Text } = Typography;

const STATUS_CONFIG: Record<string, { color: string; bg: string; border: string; icon: React.ReactNode }> = {
  pending: {
    color: 'default',
    bg: '#fafafa',
    border: '#d9d9d9',
    icon: <ClockCircleOutlined style={{ fontSize: 14 }} />,
  },
  running: {
    color: 'processing',
    bg: '#e6f4ff',
    border: '#1677ff',
    icon: <SyncOutlined spin style={{ fontSize: 14, color: '#1677ff' }} />,
  },
  passed: {
    color: 'success',
    bg: '#f6ffed',
    border: '#52c41a',
    icon: <CheckCircleOutlined style={{ fontSize: 14, color: '#52c41a' }} />,
  },
  failed: {
    color: 'error',
    bg: '#fff2f0',
    border: '#ff4d4f',
    icon: <CloseCircleOutlined style={{ fontSize: 14, color: '#ff4d4f' }} />,
  },
};

interface Props {
  steps: RunStep[];
  activeIndex: number;
  onSelect: (index: number) => void;
}

export default function StepTimeline({ steps, activeIndex, onSelect }: Props) {
  const sorted = [...steps].sort((a, b) => a.step_index - b.step_index);
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

  // Auto-scroll active step into view
  useEffect(() => {
    if (activeRef.current && containerRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [activeIndex]);

  return (
    <div ref={containerRef} style={{ padding: 12, overflowY: 'auto', height: '100%' }}>
      <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 12 }}>
        步骤时间线
      </Text>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {sorted.map((step) => {
          const isHealed = (step.output_json as Record<string, unknown> | null)?.healed === true;
          const effectiveStatus = isHealed ? 'passed' : step.status;
          const cfg = STATUS_CONFIG[effectiveStatus] ?? STATUS_CONFIG.pending;
          const isActive = step.step_index === activeIndex;
          const isRunning = step.status === 'running';

          return (
            <div
              key={step.step_index}
              ref={isActive ? activeRef : undefined}
              onClick={() => onSelect(step.step_index)}
              style={{
                cursor: 'pointer',
                padding: '10px 12px',
                borderRadius: 8,
                background: isActive ? '#e6f4ff' : cfg.bg,
                border: `2px solid ${isActive ? '#1677ff' : cfg.border}`,
                transition: 'all 0.2s ease',
                position: 'relative',
                overflow: 'hidden',
              }}
              className={isRunning ? 'step-card-running' : ''}
            >
              {/* Running pulse animation */}
              {isRunning && (
                <style>{`
                  .step-card-running {
                    animation: stepPulse 2s infinite;
                  }
                  @keyframes stepPulse {
                    0% { box-shadow: 0 0 0 0 rgba(22, 119, 255, 0.4); }
                    70% { box-shadow: 0 0 0 6px rgba(22, 119, 255, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(22, 119, 255, 0); }
                  }
                `}</style>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                {cfg.icon}
                <Text strong style={{ fontSize: 13, flex: 1 }}>
                  #{step.step_index} {step.action || '...'}
                </Text>
                <Tag
                  color={cfg.color}
                  style={{ fontSize: 11, lineHeight: '16px', padding: '0 6px', margin: 0 }}
                >
                  {isHealed ? (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <ToolOutlined style={{ fontSize: 10 }} />
                      已自愈
                    </span>
                  ) : (
                    step.status
                  )}
                </Tag>
              </div>

              {step.params_summary && (
                <Text type="secondary" style={{ fontSize: 11, display: 'block' }} ellipsis>
                  {step.params_summary}
                </Text>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                {step.duration_ms != null ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {step.duration_ms}ms
                  </Text>
                ) : (
                  <span />
                )}
                {step.error && (
                  <Text type="danger" style={{ fontSize: 11 }} ellipsis>
                    失败
                  </Text>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
