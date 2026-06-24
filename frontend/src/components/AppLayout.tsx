import { Layout, Menu } from 'antd';
import {
  ProjectOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';

const { Sider, Content } = Layout;

const menuItems = [
  {
    key: '/projects',
    icon: <ProjectOutlined />,
    label: '项目管理',
  },
  {
    key: '/settings/llm',
    icon: <SettingOutlined />,
    label: 'LLM 配置',
  },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = location.pathname.startsWith('/settings')
    ? '/settings/llm'
    : '/projects';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} theme="light">
        <div
          style={{
            height: 48,
            margin: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 18,
            color: '#1677ff',
          }}
        >
          WebBot
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Content
          style={{
            margin: 16,
            padding: 16,
            background: '#fff',
            borderRadius: 8,
            overflow: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}