import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import hi from './hi.json'

const saved = (() => {
  try {
    return localStorage.getItem('lms.locale') ?? undefined
  } catch {
    return undefined
  }
})()

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: saved ?? 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export function setLanguage(locale: 'en' | 'hi') {
  void i18n.changeLanguage(locale)
  document.documentElement.lang = locale
  if (locale === 'hi') void import('@fontsource/noto-sans-devanagari')
  try {
    localStorage.setItem('lms.locale', locale)
  } catch {
    /* ignore */
  }
}

export default i18n
