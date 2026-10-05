/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        base: {
          950: '#080a0e',
          900: '#0c1015',
          850: '#10151c',
          800: '#141a23',
          750: '#19202b',
          700: '#1e2733',
          600: '#283442',
          500: '#334155',
        },
        accent: {
          DEFAULT: '#3b82f6',
          50: '#eff6ff',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        ok: '#22c55e',
        warn: '#f59e0b',
        bad: '#ef4444',
        muted: '#8b98a9',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        xxs: '0.6875rem',
      },
    },
  },
  plugins: [],
};
