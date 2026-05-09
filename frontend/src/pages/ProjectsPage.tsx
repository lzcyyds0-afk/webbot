import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Space,
  Popconfirm,
  Typography,
  Tag,
  message,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useProjectsStore } from '../stores/projectsStore';
import type { Project } from '../types';

const { Title } = Typography;

export default function ProjectsPage() {
  const navigate = useNavigate();
  const projects = useProjectsStore((s) => s.projects);
  const loading = useProjectsStore((s) => s.loading);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);
  const createProject = useProjectsStore((s) => s.createProject);
  const deleteProject = useProjectsStore((s) => s.deleteProject);

  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const project = await createProject(values);
      setModalOpen(false);
      form.resetFields();
      message.success('项目创建成功');
      navigate(`/projects/${project.id}`);
    } catch {
      // validation error — do nothing
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: number) => {
    await deleteProject(id);
    message.success('项目已删除');
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: '项目名称',
      dataIndex: 'name',
      render: (name: string, record: Project) => (
        <Button
          type="link"
          onClick={() => navigate(`/projects/${record.id}`)}
        >
          {name}
        </Button>
      ),
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      ellipsis: true,
      render: (url: string) => (
        <Tag color="blue">{url}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right' as const,
      render: (_: unknown, record: Project) => (
        <Space size="small">
          <Button
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={() => navigate(`/projects/${record.id}`)}
          >
            详情
          </Button>
          <Popconfirm
            title="确认删除该项目？"
            description="删除后该项目下所有用例和运行记录将丢失"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button size="small" icon={<DeleteOutlined />} danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>项目列表</Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
        >
          新建项目
        </Button>
      </div>

      <Table
        rowKey="id"
        dataSource={projects}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: true }}
        scroll={{ x: 'max-content' }}
      />

      <Modal
        title="新建项目"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        confirmLoading={creating}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" autoComplete="off">
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="例如：OpenClaw 测试" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[
              { required: true, message: '请输入 Base URL' },
              { type: 'url', message: '请输入有效的 URL' },
            ]}
          >
            <Input placeholder="例如：https://www.ctyun.cn" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}