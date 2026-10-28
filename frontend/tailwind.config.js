/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#111923', 900: '#182536', 800: '#29384a', 700: '#48596d' },
        canvas: '#f2f4f6',
        line: '#d9dfe6',
        teal: { 700: '#176d68', 600: '#247d77', 100: '#dcefeb', 50: '#f1f7f6' },
        amber: { 700: '#925b18', 100: '#f4e8d1', 50: '#fbf7ef' },
        rose: { 700: '#a1444b', 100: '#f4e2e3', 50: '#fbf5f5' },
      },
      boxShadow: { panel: '0 1px 2px rgba(17, 25, 35, 0.04)' },
      fontFamily: { sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'] },
    },
  },
  plugins: [],
}
