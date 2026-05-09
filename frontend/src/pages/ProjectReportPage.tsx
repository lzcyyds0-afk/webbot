import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Segmented,
  DatePicker,
  Table,
  Tag,
  Spin,
  Statistic,
  Row,
  Col,
  Typography,
  Button,
} from 'antd';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  ArrowRightOutlined,
  ExperimentOutlined,
  FieldTimeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { fetchProjectReport } from '../api/report';
import type { ProjectReport } from '../types';

const { RangePicker } = DatePicker;
const { Title, Text } = Typography;

type DateRange = '7' | '30' | 'custom';

const PIE_COLORS = ['#52c41a', '#1677ff', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2'];

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function ProjectReportPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const navigate = useNavigate();

  const [rangeType, setRangeType] = useState<DateRange>('30');
  const [customDates, setCustomDates] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [data, setData] = useState<ProjectReport | null>(null);
  const [loading, setLoading] = useState(false);

  const dateRange = useMemo(() => {
    if (rangeType === 'custom' && customDates) {
      return {
        from: customDates[0].format('YYYY-MM-DD'),
        to: customDates[1].format('YYYY-MM-DD'),
      };
    }
    const days = rangeType === '7' ? 7 : 30;
    return {
      from: dayjs().subtract(days, 'day').format('YYYY-MM-DD'),
      to: dayjs().format('YYYY-MM-DD'),
    };
  }, [rangeType, customDates]);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    fetchProjectReport(projectId, dateRange.from, dateRange.to)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [projectId, dateRange.from, dateRange.to]);

  const kpi = data?.kpi;
  const trendData = data?.trend ?? [];
  const durationData = data?.duration_by_action ?? [];
  const failedSteps = data?.failed_steps_top ?? [];
  const actionRateData = data?.action_success_rate ?? [];
  const confidenceData = data?.ai_confidence;

  const confidenceChartData = useMemo(() => {
    if (!confidenceData) return [];
    const bins = confidenceData.bins;
    return confidenceData.counts.map((count, i) => ({
      name: `${bins[i]}-${bins[i + 1]}`,
      count,
    }));
  }, [confidenceData]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <Row justify="space-between" align="middle">
        <Title level={3} style={{ margin: 0 }}>
          项目质量报告
        </Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Segmented
            value={rangeType}
            onChange={(v) => setRangeType(v as DateRange)}
            options={[
              { label: '近7天', value: '7' },
              { label: '近30天', value: '30' },
              { label: '自定义', value: 'custom' },
            ]}
          />
          {rangeType === 'custom' && (
            <RangePicker
              value={customDates}
              onChange={(vals) => setCustomDates(vals as [dayjs.Dayjs, dayjs.Dayjs] | null)}
            />
          )}
          <Button onClick={() => navigate(`/projects/${projectId}`)}>
            返回项目
          </Button>
        </div>
      </Row>

      {loading && !data && (
        <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
      )}

      {data && (
        <>
          {/* KPI Cards */}
          <Row gutter={16}>
            <Col span={6}>
              <Card>
                <Statistic
                  title="总运行次数"
                  value={kpi?.total_runs ?? 0}
                  prefix={<ExperimentOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="通过率"
                  value={Math.round((kpi?.pass_rate ?? 0) * 100)}
                  suffix="%"
                  prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="平均耗时"
                  value={formatDuration(kpi?.avg_duration_ms ?? null)}
                  prefix={<FieldTimeOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="失败用例数"
                  value={kpi?.failed_cases ?? 0}
                  prefix={<CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
          </Row>

          {/* Charts Row 1: Trend + Pie */}
          <Row gutter={16}>
            <Col span={14}>
              <Card title="通过率趋势">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={trendData}>
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 1]} tickFormatter={(v: any) => `${(v * 100).toFixed(0)}%`} />
                    <Tooltip
                      formatter={(value: any) => [`${(value * 100).toFixed(1)}%`, '通过率']}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="pass_rate"
                      stroke="#1677ff"
                      fill="#1677ff"
                      fillOpacity={0.1}
                    />
                    <Line
                      type="monotone"
                      dataKey="pass_rate"
                      stroke="#1677ff"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="通过率"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            </Col>
            <Col span={10}>
              <Card title="Action 成功率">
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={actionRateData}
                      dataKey="total"
                      nameKey="action"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      label={(props: any) => `${props.action} ${(props.rate * 100).toFixed(0)}%`}
                    >
                      {actionRateData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(_val: any, _name: any, props: any) => {
                        const p = props?.payload;
                        return [`${p?.passed ?? 0}/${p?.total ?? 0}`, p?.action];
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </Card>
            </Col>
          </Row>

          {/* Charts Row 2: Duration Distribution */}
          <Card title="步骤耗时分布 (P50 / P95)">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={durationData}>
                <XAxis dataKey="action" />
                <YAxis tickFormatter={(v: number) => formatDuration(v)} />
                <Tooltip
                  formatter={(value: any, name: any) => [formatDuration(value), name]}
                />
                <Legend />
                <Bar dataKey="p50" name="P50" fill="#1677ff" radius={[4, 4, 0, 0]} />
                <Bar dataKey="p95" name="P95" fill="#52c41a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* Failed Steps TOP N */}
          <Card title="失败步骤 TOP N">
            <Table
              rowKey={(r) => `${r.action}-${r.selector}`}
              size="small"
              pagination={false}
              dataSource={failedSteps}
              columns={[
                { title: 'Action', dataIndex: 'action', width: 100 },
                {
                  title: 'Selector',
                  dataIndex: 'selector',
                  render: (v: string) => (
                    <Text code ellipsis style={{ maxWidth: 300, display: 'inline-block' }}>
                      {v || '-'}
                    </Text>
                  ),
                },
                {
                  title: '失败次数',
                  dataIndex: 'failure_count',
                  width: 100,
                  render: (v: number) => <Tag color="error">{v}</Tag>,
                },
                {
                  title: '最近失败',
                  dataIndex: 'last_failed_at',
                  width: 180,
                  render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
                },
                {
                  title: '操作',
                  width: 80,
                  render: (_, r) => (
                    <Button
                      type="link"
                      size="small"
                      icon={<ArrowRightOutlined />}
                      onClick={() => navigate(`/runs/${r.last_run_id}`)}
                    >
                      跳转
                    </Button>
                  ),
                },
              ]}
            />
          </Card>

          {/* AI Confidence Histogram */}
          <Card title="AI 诊断置信度分布">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={confidenceChartData}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" name="数量" fill="#722ed1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            {confidenceData?.avg != null && (
              <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 8 }}>
                平均置信度: {(confidenceData.avg * 100).toFixed(1)}%
              </Text>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
