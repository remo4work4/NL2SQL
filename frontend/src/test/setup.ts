/** vitest 全局 setup：补齐 jsdom 缺失的浏览器 API。 */
import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// antd 响应式组件依赖 matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})
