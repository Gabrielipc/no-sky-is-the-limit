import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { isLang, setCurrentLang, type Lang } from './lang';
import './language.css';

const STORAGE_KEY = 'regolith.lang';

/** `?lang=` in a shared link, then the saved choice, then the browser language. */
function initialLang(): Lang {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('lang');
    if (isLang(fromUrl)) return fromUrl;
  } catch { /* no URL */ }
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch { /* storage blocked */ }
  const browser = typeof navigator !== 'undefined' ? navigator.language || '' : '';
  return browser && !browser.toLowerCase().startsWith('es') ? 'en' : 'es';
}

type I18n = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Spanish text first, English second. */
  t: (es: string, en: string) => string;
};
const Context = createContext<I18n | null>(null);

const TITLES: Record<Lang, string> = {
  es: 'Regolith · Tres cuerpos, un mismo suelo',
  en: 'Regolith · Three bodies, one ground',
};

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  // Module-level formatters read the language during this same render.
  setCurrentLang(lang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = TITLES[lang];
    try { window.localStorage.setItem(STORAGE_KEY, lang); } catch { /* storage blocked */ }
  }, [lang]);
  const setLang = useCallback((next: Lang) => { setCurrentLang(next); setLangState(next); }, []);
  const value = useMemo<I18n>(() => ({ lang, setLang, t: (es, en) => (lang === 'en' ? en : es) }), [lang, setLang]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(Context);
  if (!value) throw new Error('useI18n must be used inside I18nProvider');
  return value;
}

/** ES | EN switch, used in the explorer header and in the landing navigation. */
export function LanguageSwitch({ className = '' }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div className={`lang-switch ${className}`.trim()} role="group" aria-label={t('Idioma', 'Language')}>
      {(['es', 'en'] as const).map(code => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={lang === code}
          aria-label={code === 'es' ? 'Español' : 'English'}
          title={code === 'es' ? 'Español' : 'English'}
          onClick={() => setLang(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
