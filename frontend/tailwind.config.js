/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ops: {
          bg: '#0b1220',
          panel: '#111a2e',
          panelLight: '#16213a',
          border: '#233252',
          accent: '#22d3ee',
          accentDim: '#0e7490',
          danger: '#ef4444',
          warning: '#f59e0b',
          success: '#22c55e',
          text: '#e2e8f0',
          textDim: '#94a3b8',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
