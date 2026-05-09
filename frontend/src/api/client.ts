import axios from 'axios';
import { message } from 'antd';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
});

// ── Request interceptor ──
client.interceptors.request.use((config) => {
  return config;
});

// ── Response interceptor ──
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    const detail =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message;

    if (status === 404) {
      message.error(`资源不存在: ${detail}`);
    } else if (status === 422) {
      message.error(`参数错误: ${detail}`);
    } else if (status && status >= 500) {
      message.error(`服务器错误: ${detail}`);
    } else if (!err.response) {
      message.error(`网络错误: ${detail}`);
    }

    return Promise.reject(err);
  },
);

export default client;
