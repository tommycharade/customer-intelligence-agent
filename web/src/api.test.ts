import { describe, expect, it } from 'vitest'
import { errorMessage, safeLink } from './api'

describe('untrusted content at the UI boundary', () => {
  it('allows only HTTP(S) evidence links', () => {
    expect(safeLink('https://company.com/docs')).toBe('https://company.com/docs')
    expect(safeLink('javascript:alert(1)')).toBeUndefined()
    expect(safeLink('file:///etc/passwd')).toBeUndefined()
    expect(safeLink(null)).toBeUndefined()
  })
  it('turns validation failures into readable messages', () => {
    expect(errorMessage([{msg: 'Enter a company type'}, {msg: 'Enter exclusions'}])).toBe('Enter a company type Enter exclusions')
    expect(errorMessage({untrusted: 'not a string'})).toContain('try again')
  })
})
