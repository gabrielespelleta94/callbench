import type { SVGProps } from 'react'

const base = (p: SVGProps<SVGSVGElement>) => ({
  width: 14,
  height: 14,
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
  ...p,
})

type P = SVGProps<SVGSVGElement>

export const IconSwap = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 5.5h9.5M10 3l2.5 2.5L10 8M13 10.5H3.5M6 8l-2.5 2.5L6 13" />
  </svg>
)
export const IconChevron = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 6l4 4 4-4" />
  </svg>
)
export const IconClose = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
)
export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="M3.5 8.5l3 3 6-7" />
  </svg>
)
export const IconX = (p: P) => (
  <svg {...base(p)}>
    <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
  </svg>
)
export const IconMinus = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 8h8" />
  </svg>
)
export const IconAlert = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 2.5l6 10.5H2L8 2.5zM8 6.8v2.6M8 11.3v.1" />
  </svg>
)
export const IconShieldCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 1.8l5 1.9v4c0 3-2.1 5.1-5 6.5-2.9-1.4-5-3.5-5-6.5v-4l5-1.9zM5.7 8l1.7 1.7L10.6 6.4" />
  </svg>
)
export const IconShieldX = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 1.8l5 1.9v4c0 3-2.1 5.1-5 6.5-2.9-1.4-5-3.5-5-6.5v-4l5-1.9zM6.2 6.2l3.6 3.6M9.8 6.2l-3.6 3.6" />
  </svg>
)
export const IconShieldQ = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 1.8l5 1.9v4c0 3-2.1 5.1-5 6.5-2.9-1.4-5-3.5-5-6.5v-4l5-1.9zM6.7 6.6a1.4 1.4 0 112 1.3c-.5.3-.7.6-.7 1.1M8 10.8v.1" />
  </svg>
)
export const IconPrev = (p: P) => (
  <svg {...base(p)}>
    <path d="M10 3.5L5.5 8l4.5 4.5" />
  </svg>
)
export const IconNext = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 3.5L10.5 8 6 12.5" />
  </svg>
)
export const IconWaveOff = (p: P) => (
  <svg {...base({ width: 20, height: 20, ...p })}>
    <path d="M2.5 8v0M5 6v4M8 3.5v9M11 5.5v5M13.5 7.5v1" />
  </svg>
)
export const IconRefresh = (p: P) => (
  <svg {...base(p)}>
    <path d="M13 3.5v3h-3M3 12.5v-3h3M12.4 6.5A5 5 0 004 5.2M3.6 9.5A5 5 0 0012 10.8" />
  </svg>
)

export function Mark() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--surface-3)" />
      <path
        d="M9 16v0M12.5 12v8M16 8v16M19.5 12.5v7M23 15v2"
        stroke="var(--cand)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}
