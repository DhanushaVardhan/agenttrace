/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        ink: {
          950: '#08090c',
          900: '#0c0e13',
          850: '#11141b',
          800: '#161a23',
          700: '#1e232e',
          600: '#2a3040',
          500: '#3a4258',
        },
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgba(129,140,248,0.55)' },
          '70%': { boxShadow: '0 0 0 7px rgba(129,140,248,0)' },
          '100%': { boxShadow: '0 0 0 0 rgba(129,140,248,0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 220ms ease-out both',
        'pulse-ring': 'pulse-ring 1.6s ease-out infinite',
      },
    },
  },
  plugins: [],
}
