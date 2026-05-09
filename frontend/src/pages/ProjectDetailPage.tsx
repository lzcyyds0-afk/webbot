import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { BarChartOutlined, CompassOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { Layout, Typography, Tag, Spin, Button } from 'antd';
import { useProjectsStore } from '../stores/projectsStore';
import TestCaseList from '../components/TestCaseList';
import TestCaseEditor from '../components/TestCaseEditor';
import AIScoutModal from '../components/AIScoutModal';

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

export default function ProjectDetailPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const navigate = useNavigate();
  const [scoutOpen, setScoutOpen] = useState(false);

  const currentProject = useProjectsStore((s) => s.currentProject);
  const testCases = useProjectsStore((s) => s.testCases);
  const currentTestCase = useProjectsStore((s) => s.currentTestCase);
  const loading = useProjectsStore((s) => s.loading);
  const fetchProject = useProjectsStore((s) => s.fetchProject);
  const fetchTestCases = useProjectsStore((s) => s.fetchTestCases);
  const setCurrentProject = useProjectsStore((s) => s.setCurrentProject);
  const setCurrentTestCase = useProjectsStore((s) => s.setCurrentTestCase);

  useEffect(() => {
    if (!projectId) return;
    fetchProject(projectId).then((p) => setCurrentProject(p)).catch(() => navigate('/projects'));
    fetchTestCases(projectId);
    return () => {
      setCurrentProject(null);
      setCurrentTestCase(null);
    };
  }, [projectId, fetchProject, fetchTestCases, setCurrentProject, setCurrentTestCase, navigate]);

  const handleSelectCase = (caseId: number) => {
    const tc = testCases.find((c) => c.id === caseId) ?? null;
    setCurrentTestCase(tc);
  };

  if (loading && !currentProject) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>
            返回
          </Button>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              {currentProject?.name ?? `项目 #${projectId}`}
            </Title>
            {currentProject?.base_url && (
              <Tag color="blue" style={{ marginTop: 4 }}>
                {currentProject.base_url}
              </Tag>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            icon={<CompassOutlined />}
            onClick={() => setScoutOpen(true)}
          >
            AI 探索
          </Button>
          <Button
            icon={<BarChartOutlined />}
            onClick={() => navigate(`/projects/${projectId}/report`)}
          >
            质量报告
          </Button>
        </div>
      </div>

      {/* Body: Sider + Content */}
      <Layout style={{ flex: 1, background: 'transparent' }}>
        <Sider
          width={280}
          style={{ background: '#fafafa', borderRadius: 8, marginRight: 12, overflow: 'auto' }}
        >
          <TestCaseList
            projectId={projectId}
            testCases={testCases}
            selectedId={currentTestCase?.id ?? null}
            onSelect={handleSelectCase}
          />
        </Sider>
        <Content style={{ background: 'transparent' }}>
          {currentTestCase ? (
            <TestCaseEditor projectId={projectId} testCase={currentTestCase} />
          ) : (
            <div style={{ color: '#999', textAlign: 'center', marginTop: 80 }}>
              <Text type="secondary">请从左侧选择或新建一个用例</Text>
            </div>
          )}
        </Content>
      </Layout>

      <AIScoutModal
        open={scoutOpen}
        projectId={projectId}
        baseUrl={currentProject?.base_url ?? ''}
        onClose={() => setScoutOpen(false)}
      />
    </div>
  );
}
