export function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(x => typeof x?.msg === 'string' ? x.msg : 'Check the supplied value.').join(' ')
  return 'The request could not finish. Check your connection and try again.'
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, {
    ...options, credentials: 'same-origin',
    headers: options.body instanceof FormData ? options.headers : {'Content-Type': 'application/json', ...options.headers},
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(errorMessage(body.detail))
  }
  return response.json()
}

export const send = <T>(path: string, data?: unknown, method = 'POST') => api<T>(path, {method, body: data === undefined ? undefined : JSON.stringify(data)})
export const dateLabel = (value: string | null) => {
  const date = value ? new Date(value) : null
  return date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'short', year: 'numeric'}).format(date) : 'Unknown'
}
export const money = (value: number) => '$' + value.toFixed(2)
export const statusLabel = (value: string) => value.replaceAll('_', ' ').replace(/^./, x => x.toUpperCase())

export function safeLink(value: string | null): string | undefined {
  if (!value) return undefined
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}
