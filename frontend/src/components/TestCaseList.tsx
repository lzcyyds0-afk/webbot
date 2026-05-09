import { useState } from 'react';
import { List, Button, Modal, Form, Input, Popconfirm, Typography, Empty } from 'antd';
import { PlusOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons';
import { useProjectsStore } from '../stores/projectsStore';
import type { TestCase } from '../types';

const { Text } = Typography;

interface Props {
  projectId: number;
  testCases: TestCase[];
  selectedId: number | null;
  onSelect: (caseId: number) => void;
}

export default function TestCaseList({ projectId, testCases, selectedId, onSelect }: Props) {
  const createTestCase = useProjectsStore((s) => s.createTestCase);
  const deleteTestCase = useProjectsStore((s) => s.deleteTestCase);
  const setCurrentTestCase = useProjectsStore((s) => s.setCurrentTestCase);

  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const tc = await createTestCase(projectId, { name: values.name });
      setModalOpen(false);
      form.resetFields();
      onSelect(tc.id);
    } catch {
      // validation
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (caseId: number) => {
    await deleteTestCase(projectId, caseId);
    if (selectedId === caseId) {
      setCurrentTestCase(null);
    }
  };

  return (
    <div style={{ padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Text strong style={{ fontSize: 14 }}>用例列表</Text>
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建
        </Button>
      </div>

      {testCases.length === 0 ? (
        <Empty description="暂无用例" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={testCases}
          renderItem={(tc) => (
            <List.Item
              style={{
                padding: '6px 8px',
                borderRadius: 4,
                cursor: 'pointer',
                background: tc.id === selectedId ? '#e6f4ff' : 'transparent',
              }}
              onClick={() => onSelect(tc.id)}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  <FileTextOutlined style={{ marginRight: 6, color: '#1677ff' }} />
                  <Text ellipsis>{tc.name}</Text>
                </div>
                <Popconfirm
                  title="删除该用例？"
                  onConfirm={(e) => { e?.stopPropagation(); handleDelete(tc.id); }}
                  onCancel={(e) => e?.stopPropagation()}
                  okText="删除"
                  cancelText="取消"
                >
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              </div>
            </List.Item>
          )}
        />
      )}

      <Modal
        title="新建用例"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        confirmLoading={creating}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="用例名称"
            rules={[{ required: true, message: '请输入用例名称' }]}
          >
            <Input placeholder="例如：登录流程测试" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}