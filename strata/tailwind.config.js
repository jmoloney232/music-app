/** @type {import('tailwindcss').Config} */
// Booth direction: dark ground, one gold accent, colour as stroke and small
// marks — never a filled block. Semantic names kept from the previous theme so
// most JSX reskins by value alone.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        canvas:      '#1A1918',
        surface:     '#1A1918',
        sunken:      '#201F1E',
        tan:         '#2D2B2B',
        ink:         '#F3F2F2',
        'ink-soft':  '#BAB6B6',
        'ink-quiet': '#9B9797',
        'ink-muted': '#7D7979',
        'ink-dim':   '#605D5D',
        hairline:    'rgba(243,242,242,0.10)',
        'line-control': 'rgba(243,242,242,0.24)',
        'line-strong':  'rgba(243,242,242,0.24)',
        divider:     'rgba(243,242,242,0.14)',
        accent:       '#E1AD66',
        'accent-deep': '#FACB8D',
        'accent-fill': '#3A270D',
        success:      '#7BC98B',
        error:        '#E5736B',
        spotify:      '#1DB954',
      },
      fontFamily: {
        sans: ['Lora', 'Georgia', 'serif'],
        display: ['"Cormorant Garamond"', 'Georgia', 'serif'],
        // No monospace in Booth — figures align via font-variant tabular-nums.
        mono: ['Lora', 'Georgia', 'serif'],
      },
      fontSize: {
        xs:   ['12px', '1.4'],
        sm:   ['13px', '1.5'],
        base: ['14px', '1.7'],
        md:   ['16px', '1.5'],
        lg:   ['22px', '1.3'],
        xl:   ['30px', '1.15'],
        '2xl': ['44px', '1.05'],
        '3xl': ['56px', '1.0'],
      },
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
        panel:   '4px',
      },
      // Booth has no shadows: elevation is expressed with 1px rules only.
      boxShadow: {
        raised:  'none',
        overlay: 'none',
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
