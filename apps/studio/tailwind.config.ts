import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Driven by CSS custom properties in src/lib/theme.css
        bg: 'var(--bg)',
        fg: 'var(--fg)',
        'muted-fg': 'var(--muted-fg)',
        accent: 'var(--accent)',
        'accent-fg': 'var(--accent-fg)',
        border: 'var(--border)',
        ring: 'var(--ring)',
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
      },
      transitionDuration: {
        quick: '100ms',
        base: '200ms',
        lazy: '400ms',
      },
      transitionTimingFunction: {
        'pdlc-out': 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};

export default config;
