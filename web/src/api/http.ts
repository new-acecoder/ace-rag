import axios from 'axios'

export interface ApiError {
  code: string
  message: string
}

export const http = axios.create({
  baseURL: '/api/v1',
})

export function toApiError(error: unknown): ApiError {
  if (axios.isAxiosError<ApiError>(error) && error.response?.data?.code) {
    return error.response.data
  }

  return {
    code: 'NETWORK_ERROR',
    message: '无法连接到服务，请确认后端已启动。',
  }
}
