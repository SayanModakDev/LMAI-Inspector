import React from 'react';
import { BRAND_CONFIG } from '../constants/branding';
import './BrandLogo.css';

/**
 * Reusable Brand Logo component for LMAI Inspector.
 * Supported variants:
 * - 'horizontal' (default primary logo: emblem + LMAI INSPECTOR)
 * - 'tagline' (marketing/presentation lockup with full descriptor)
 * - 'mark' (emblem only, ideal for icons, avatars, loading)
 * - 'compact' (stacked lockup for mobile/narrow spaces)
 * - 'dark' (high-contrast version for dark backgrounds)
 * - 'white' (monochrome white)
 * - 'black' (monochrome black)
 */
export const BrandLogo = ({
  variant = 'horizontal',
  className = '',
  height,
  width,
  style = {},
  usePng = false,
  alt,
  ...props
}) => {
  let src = BRAND_CONFIG.assets.logo.svg;
  let defaultAlt = BRAND_CONFIG.name;
  let defaultAspect = '620 / 160';

  switch (variant) {
    case 'tagline':
      src = usePng ? BRAND_CONFIG.assets.logoTagline.png : BRAND_CONFIG.assets.logoTagline.svg;
      defaultAlt = BRAND_CONFIG.assets.logoTagline.alt;
      defaultAspect = '900 / 860';
      break;
    case 'mark':
      src = usePng ? BRAND_CONFIG.assets.mark.png : BRAND_CONFIG.assets.mark.svg;
      defaultAlt = BRAND_CONFIG.assets.mark.alt;
      defaultAspect = '1 / 1';
      break;
    case 'compact':
      src = usePng ? BRAND_CONFIG.assets.compact.png : BRAND_CONFIG.assets.compact.svg;
      defaultAlt = BRAND_CONFIG.assets.compact.alt;
      defaultAspect = '440 / 300';
      break;
    case 'dark':
      src = usePng ? BRAND_CONFIG.assets.dark.logoPng : BRAND_CONFIG.assets.dark.logoSvg;
      defaultAlt = `${BRAND_CONFIG.name} (Dark Mode)`;
      defaultAspect = '620 / 160';
      break;
    case 'mark-dark':
      src = usePng ? BRAND_CONFIG.assets.dark.markPng : BRAND_CONFIG.assets.dark.markSvg;
      defaultAlt = `${BRAND_CONFIG.name} Mark (Dark Mode)`;
      defaultAspect = '1 / 1';
      break;
    case 'white':
      src = usePng ? BRAND_CONFIG.assets.white.logoPng : BRAND_CONFIG.assets.white.logoSvg;
      defaultAlt = `${BRAND_CONFIG.name} (White)`;
      defaultAspect = '620 / 160';
      break;
    case 'black':
      src = usePng ? BRAND_CONFIG.assets.black.logoPng : BRAND_CONFIG.assets.black.logoSvg;
      defaultAlt = `${BRAND_CONFIG.name} (Black)`;
      defaultAspect = '620 / 160';
      break;
    case 'horizontal':
    default:
      src = usePng ? BRAND_CONFIG.assets.logo.png : BRAND_CONFIG.assets.logo.svg;
      defaultAlt = BRAND_CONFIG.assets.logo.alt;
      defaultAspect = '620 / 160';
      break;
  }

  const combinedStyle = {
    aspectRatio: defaultAspect,
    height: height ? (typeof height === 'number' ? `${height}px` : height) : undefined,
    width: width ? (typeof width === 'number' ? `${width}px` : width) : undefined,
    objectFit: 'contain',
    ...style,
  };

  return (
    <img
      src={src}
      alt={alt !== undefined ? alt : defaultAlt}
      className={`lmai-brand-logo lmai-brand-logo--${variant} ${className}`}
      style={combinedStyle}
      loading="eager"
      {...props}
    />
  );
};

export default BrandLogo;
