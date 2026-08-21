import type { ApiSseRecord } from '@/types/sse'

export async function consumeSse(
  response: Response,
  onEvent: (event: ApiSseRecord) => void,
): Promise<void> {
  if (!response.body) throw new Error('服务未返回 SSE 数据流。')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseSseFrame(frame)
        if (event) onEvent(event)
        boundary = buffer.indexOf('\n\n')
      }

      if (done) break
    }
  } finally {
    reader.releaseLock()
  }
}

function parseSseFrame(frame: string): ApiSseRecord | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (dataLines.length === 0) return null

  const data = JSON.parse(dataLines.join('\n'))
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('SSE 数据格式错误。')
  }
  return { event, data: data as Record<string, unknown> }
}
