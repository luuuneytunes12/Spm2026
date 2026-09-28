// Mirror of backend/app/core/phone.py -- keep dial codes and digit ranges
// byte-identical. The backend is the authority on what is valid; this list
// only drives the country <select> and lets the UI show the expected
// length as a hint. Not exhaustive -- a reasonable set for this project.

export interface PhoneCountry {
  code: string
  label: string
  minDigits: number
  maxDigits: number
}

export const PHONE_COUNTRIES: PhoneCountry[] = [
  { code: '+65', label: 'Singapore (+65)', minDigits: 8, maxDigits: 8 },
  { code: '+60', label: 'Malaysia (+60)', minDigits: 9, maxDigits: 10 },
  { code: '+1', label: 'US/Canada (+1)', minDigits: 10, maxDigits: 10 },
  { code: '+44', label: 'United Kingdom (+44)', minDigits: 10, maxDigits: 10 },
  { code: '+61', label: 'Australia (+61)', minDigits: 9, maxDigits: 9 },
  { code: '+91', label: 'India (+91)', minDigits: 10, maxDigits: 10 },
  { code: '+86', label: 'China (+86)', minDigits: 11, maxDigits: 11 },
  { code: '+81', label: 'Japan (+81)', minDigits: 10, maxDigits: 10 },
  { code: '+62', label: 'Indonesia (+62)', minDigits: 9, maxDigits: 12 },
  { code: '+63', label: 'Philippines (+63)', minDigits: 10, maxDigits: 10 },
  { code: '+66', label: 'Thailand (+66)', minDigits: 9, maxDigits: 9 },
  { code: '+84', label: 'Vietnam (+84)', minDigits: 9, maxDigits: 10 },
  { code: '+852', label: 'Hong Kong (+852)', minDigits: 8, maxDigits: 8 },
  { code: '+886', label: 'Taiwan (+886)', minDigits: 9, maxDigits: 9 },
  { code: '+82', label: 'South Korea (+82)', minDigits: 9, maxDigits: 10 },
  { code: '+49', label: 'Germany (+49)', minDigits: 10, maxDigits: 11 },
  { code: '+33', label: 'France (+33)', minDigits: 9, maxDigits: 9 },
  { code: '+971', label: 'United Arab Emirates (+971)', minDigits: 9, maxDigits: 9 },
  { code: '+64', label: 'New Zealand (+64)', minDigits: 8, maxDigits: 9 },
  { code: '+966', label: 'Saudi Arabia (+966)', minDigits: 9, maxDigits: 9 },
]

export const PHONE_DIGIT_RANGE: Record<string, [number, number]> = Object.fromEntries(
  PHONE_COUNTRIES.map((c) => [c.code, [c.minDigits, c.maxDigits]]),
)

/** Human-readable expected length, e.g. "8 digits" or "9-10 digits". */
export function expectedDigitsLabel(code: string): string | null {
  const range = PHONE_DIGIT_RANGE[code]
  if (!range) return null
  const [low, high] = range
  return low === high ? `${low} digits` : `${low}-${high} digits`
}
