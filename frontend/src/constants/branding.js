/**
 * Centralized Branding System Configuration for LMAI Inspector.
 * Master brand reference assets and paths.
 */

export const BRAND_CONFIG = {
  name: 'LMAI Inspector',
  fullName: 'Legal Metrology AI Inspector',
  tagline: 'Legal Metrology • Packaged Commodities',
  subTagline: 'Compliance Screening',
  disclaimer:
    'This system is an inspection-support tool. Final legal verification must be made by an authorized inspector.',
  themeColors: {
    primary: '#0B2545',
    accentGreen: '#10B981',
    accentTeal: '#0D9488',
    accentBlue: '#0284C7',
    darkBg: '#0F172A',
  },
  assets: {
    // Primary Web Logo (Horizontal)
    logo: {
      svg: '/branding/lmai-inspector-logo.svg',
      png: '/branding/lmai-inspector-logo.png',
      alt: 'LMAI Inspector Logo',
    },
    // Full Marketing / Presentation Lockup
    logoTagline: {
      svg: '/branding/lmai-inspector-logo-tagline.svg',
      png: '/branding/lmai-inspector-logo-tagline.png',
      alt: 'LMAI Inspector - Legal Metrology Packaged Commodities Compliance Screening',
    },
    // Icon-Only Emblem
    mark: {
      svg: '/branding/lmai-inspector-mark.svg',
      png: '/branding/lmai-inspector-mark.png',
      alt: 'LMAI Inspector Brand Mark',
    },
    // Compact Wordmark
    compact: {
      svg: '/branding/lmai-inspector-compact.svg',
      png: '/branding/lmai-inspector-compact.png',
      alt: 'LMAI Inspector Compact',
    },
    // Dark Mode Variants
    dark: {
      logoSvg: '/branding/lmai-inspector-logo-dark.svg',
      logoPng: '/branding/lmai-inspector-logo-dark.png',
      markSvg: '/branding/lmai-inspector-mark-dark.svg',
      markPng: '/branding/lmai-inspector-mark-dark.png',
    },
    // Monochrome Variants
    white: {
      logoSvg: '/branding/lmai-inspector-white.svg',
      logoPng: '/branding/lmai-inspector-white.png',
      markSvg: '/branding/lmai-inspector-mark-white.svg',
      markPng: '/branding/lmai-inspector-mark-white.png',
    },
    black: {
      logoSvg: '/branding/lmai-inspector-black.svg',
      logoPng: '/branding/lmai-inspector-black.png',
      markSvg: '/branding/lmai-inspector-mark-black.svg',
      markPng: '/branding/lmai-inspector-mark-black.png',
    },
    // Social / Open Graph Card
    og: {
      png: '/branding/lmai-inspector-og.png',
      width: 1200,
      height: 630,
    },
    // Report / Print Asset
    report: {
      png: '/branding/lmai-inspector-report.png',
    },
    // Favicon and App Icons
    icons: {
      faviconSvg: '/favicon.svg',
      faviconIco: '/favicon.ico',
      favicon16: '/icons/favicon-16x16.png',
      favicon32: '/icons/favicon-32x32.png',
      favicon48: '/icons/favicon-48x48.png',
      pwa192: '/icons/icon-192.png',
      pwa512: '/icons/icon-512.png',
    },
  },
};

export default BRAND_CONFIG;
