/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-base':     'var(--bg-base)',
        'bg-surface':  'var(--bg-surface)',
        'bg-card':     'var(--bg-card)',
        'bg-border':   'var(--bg-border)',
        'text-primary':   'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'accent-brand':   'var(--accent-brand)',
        'cat-dry':      'var(--cat-dry)',
        'cat-drizzle':  'var(--cat-drizzle)',
        'cat-moderate': 'var(--cat-moderate)',
        'cat-heavy':    'var(--cat-heavy)',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'monospace'],
        sans: ['"DM Sans"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
