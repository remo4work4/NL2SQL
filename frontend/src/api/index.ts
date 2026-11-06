/**
 * mock 开关：Phase 0/1 默认 true（纯前端 mock 数据运行），
 * Phase 3 联调时在 .env.local 中设 VITE_USE_MOCK=false 切到真实后端。
 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'
