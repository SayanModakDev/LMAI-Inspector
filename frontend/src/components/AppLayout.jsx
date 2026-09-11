import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Menu, X, Plus, ShieldCheck, Scale } from 'lucide-react';
import Sidebar from './Sidebar';
import BrandLogo from './BrandLogo';
import { BRAND_CONFIG } from '../constants/branding';
import './AppLayout.css';

const AppLayout = ({ children }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [profile, setProfile] = useState(() => {
    try {
      const saved = localStorage.getItem('lmai_inspector_profile');
      if (saved) return JSON.parse(saved);
    } catch (_) {
      // fallback to default profile
    }
    return { name: 'Workspace User', badge: 'Not configured' };
  });
  const location = useLocation();

  useEffect(() => {
    const handleStorage = () => {
      try {
        const saved = localStorage.getItem('lmai_inspector_profile');
        if (saved) setProfile(JSON.parse(saved));
      } catch (_) {
        // ignore storage parse errors
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const getPageTitle = (pathname) => {
    if (pathname === '/' || pathname === '/dashboard') return 'Inspection Overview';
    if (pathname === '/scan') return 'New Package Inspection';
    if (pathname === '/processing') return 'Evidence Analysis in Progress';
    if (pathname.startsWith('/result')) return 'Compliance Inspection Workstation';
    if (pathname === '/history') return 'Inspection History Registry';
    if (pathname === '/reports') return 'Inspection Reports & Summaries';
    if (pathname === '/rules') return 'Legal Metrology Rule Matrix';
    if (pathname === '/settings') return 'Inspector Profile & System Settings';
    if (pathname === '/about') return 'About LMAI Inspector';
    return 'LMAI Inspector';
  };

  return (
    <div className="app-layout">
      {/* Desktop Sidebar */}
      <div className="app-layout__sidebar-desktop">
        <Sidebar />
      </div>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div className="mobile-drawer-overlay" onClick={() => setMobileMenuOpen(false)}>
          <div className="mobile-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-drawer__header">
              <BrandLogo variant="horizontal" height={28} alt="LMAI Inspector" />
              <button
                type="button"
                className="btn btn-icon-only btn-outline"
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Close navigation"
              >
                <X size={18} />
              </button>
            </div>
            <Sidebar onCloseMobile={() => setMobileMenuOpen(false)} />
          </div>
        </div>
      )}

      {/* Main Column */}
      <div className="app-layout__main-column">
        {/* Top Context Bar */}
        <header className="app-topbar">
          <div className="app-topbar__left">
            <button
              type="button"
              className="btn btn-icon-only btn-outline mobile-menu-btn"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu size={20} />
            </button>
            <div className="page-context">
              <h1 className="page-context__title">{getPageTitle(location.pathname)}</h1>
              <span className="page-context__crumb">{BRAND_CONFIG.legalStandard}</span>
            </div>
          </div>

          <div className="app-topbar__right">
            <Link to="/scan" className="btn btn-primary btn-sm topbar-cta">
              <Plus size={14} /> New Inspection
            </Link>
            <Link to="/settings" className="topbar-inspector-pill" title="Configure Inspector Profile">
              <ShieldCheck size={14} className="text-primary" />
              <span>{profile.name || 'Inspector Profile'}</span>
            </Link>
          </div>
        </header>

        {/* Dynamic Page Content */}
        <main className="app-workspace">
          {children}
        </main>

        {/* Bottom Statutory Status / Disclaimer Bar */}
        <footer className="app-system-footer">
          <div className="footer-disclaimer">
            <Scale size={13} className="footer-icon" />
            <span>
              <strong>Statutory Notice:</strong> {BRAND_CONFIG.disclaimer}
            </span>
          </div>
          <div className="footer-meta font-mono">
            LMAI Inspector Engine v1.0.0
          </div>
        </footer>
      </div>
    </div>
  );
};

export default AppLayout;
