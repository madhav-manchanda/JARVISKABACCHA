export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg: '#000000',           // Pure Black
          bgSecondary: '#121212',  // Deep Charcoal
          primary: '#a855f7',      // Electric Purple
          cyan: '#a855f7',         // Alias cyan to primary for backwards compatibility
          blue: '#a855f7',
          secondary: '#10b981',    // Emerald Green
          accent: '#a855f7',
          alert: '#F59E0B',
          textMain: '#FFFFFF',
          textMuted: '#9CA3AF'
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        montserrat: ['Montserrat', 'sans-serif'],
        mono: ['Fira Code', 'monospace']
      }
    },
  },
  plugins: [],
}
