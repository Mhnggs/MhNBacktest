/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0b0f17',
        panel: '#111827',
        border: '#1f2937',
        accent: '#22d3ee',
        good: '#22c55e',
        bad: '#ef4444',
        warn: '#f59e0b',
      },
    },
  },
  plugins: [],
}
