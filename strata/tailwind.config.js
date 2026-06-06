/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        background:       '#0A0A0A',
        surface:          '#141414',
        'surface-2':      '#1E1E1E',
        border:           '#2A2A2A',
        'purple-primary': '#7B2FBE',
        'purple-light':   '#A855F7',
        'text-primary':   '#F5F5F5',
        'text-secondary': '#A0A0A0',
        'text-subtle':    '#606060',
        success:          '#22c55e',
        warning:          '#f59e0b',
      },
      fontFamily: {
        headline: ['Space Grotesk', 'sans-serif'],
        body:     ['Inter', 'sans-serif'],
        mono:     ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}

