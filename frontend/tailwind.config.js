export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg: '#0A0A0F',
          bgSecondary: '#12121A',
          cyan: '#00F2FE',
          blue: '#4FACFE',
          accent: '#00F2FE',
          alert: '#F59E0B',
          textMain: '#F3F4F6',
          textMuted: '#9CA3AF'
        }
      },
      fontFamily: {
        sans: ['Inter', 'Outfit', 'sans-serif'],
        mono: ['Fira Code', 'monospace']
      }
    },
  },
  plugins: [],
}
