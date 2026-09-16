import axios from "axios"
import { ElMessage } from "element-plus"

export const TOKEN_KEY = "access_token"

const client = axios.create({
  baseURL: "/api/v1",
  timeout: 120_000,
})

// 原生 fetch 的认证包装：自动带 token + 统一 401 处理（清 token 跳登录）。
// 用于无法走 axios 拦截器的场景：SSE 流式读取、文件下载（blob）。
export async function authorizedFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = localStorage.getItem(TOKEN_KEY) || ""
  const resp = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.headers || {}),
    },
  })
  if (resp.status === 401) {
    localStorage.removeItem(TOKEN_KEY)
    if (!location.pathname.startsWith("/login")) {
      location.href = "/login"
    }
  }
  return resp
}

// 请求拦截：附带 token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 清 token 跳登录；其余错误（含 403 业务拒绝）统一提示
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    const msg =
      typeof detail === "string"
        ? detail
        : error.message === "Network Error"
          ? "网络错误，请检查后端服务是否启动"
          : error.message
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (!location.pathname.startsWith("/login")) {
        location.href = "/login"
      }
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default client
