/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        canvas:      '#F7E8D5',
        surface:     '#FFFFFF',
        sunken:      '#EEDFCB',
        tan:         '#FBDFC0',
        ink:         '#1B1815',
        'ink-quiet': '#5C544B',
        'ink-muted': '#695F55',
        hairline:    '#E0CDB4',
        'line-control': '#8E7F6E',
        'line-strong':  '#CCBEB1',
        accent:       '#A8442A',
        'accent-deep': '#8C3721',
        success:      '#2F6B3A',
        error:        '#9E2B25',
        spotify:      '#12833B',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        // 1.2 ratio from a 15px body
        xs:   ['12px', '1.35'],
        sm:   ['13px', '1.45'],
        base: ['15px', '1.5'],
        md:   ['18px', '1.4'],
        lg:   ['22px', '1.3'],
        xl:   ['28px', '1.2'],
        '2xl': ['40px', '1.1'],
        '3xl': ['56px', '1.05'],
      },
      // Named so they never collide with Tailwind's own numeric scale.
      // Derived from real control sizing: 15px body on a 22px line box,
      // a 56px two-line track row, 20px tags, a 48px search field.
      spacing: {
        s1: '4px',
        s2: '8px',
        s3: '12px',
        s4: '20px',
        s5: '32px',
        s6: '48px',
        'control-sm': '28px',
        control:      '36px',
        'control-lg': '48px',
      },
      maxWidth: {
        read:  '760px',
        dense: '1160px',
      },
      borderRadius: {
        DEFAULT: '4px',
        chip:    '2px',
        panel:   '10px',
      },
      boxShadow: {
        raised:  '0 1px 2px rgba(27,24,21,0.06), 0 4px 12px rgba(27,24,21,0.08)',
        overlay: '0 8px 32px rgba(27,24,21,0.16)',
      },
      transitionTimingFunction: {
        DEFAULT: 'cubic-bezier(0.2, 0, 0, 1)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
        panel:   '250ms',
      },
    },
  },
  plugins: [],
}
