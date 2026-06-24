import axios from 'axios';
import { message } from 'antd';

// Opt-out flag for the global error toast, set per-request. Use it for calls
// where a 404/empty result is an expected, non-error outcome (e.g. probing
// whether a step has a diagnosis yet) so users aren't shown a scary toast.
declare module 'axios' {
  export interface AxiosRequestConfig {
    skipErrorToast?: boolean;
  }
}

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
});

// ── Response interceptor ──
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (!err.config?.skipErrorToast) {
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
    }

    return Promise.reject(err);
  },
);

export default client;
