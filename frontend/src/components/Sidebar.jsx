import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  ScanLine,
  History,
  FileText,
  Scale,
  Settings,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import BrandLogo from './BrandLogo';
import { useSystemHealth } from '../context/SystemHealthContext';
import './Sidebar.css';

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/scan', label: 'New Inspection', icon: ScanLine, highlight: true },
  { path: '/history', label: 'Inspection History', icon: History },
  { path: '/reports', label: 'Reports Center', icon: FileText },
  { path: '/rules', label: 'Rule Matrix', icon: Scale },
  { path: '/settings', label: 'Settings & Profile', icon: Settings },
];

const Sidebar = ({ onCloseMobile }) => {
  const { healthState } = useSystemHealth();
  const [profile, setProfile] = useState(() => {
    try {
      const saved = localStorage.getItem('lmai_inspector_profile');
      if (saved) return JSON.parse(saved);
    } catch (_) {}
    return { name: 'Workspace User', badge: 'Not configured', station: 'Local Workstation' };
  });

  // Listen for profile updates in localStorage if modified in Settings
  useEffect(() => {
    const handleStorage = () => {
      try {
        const saved = localStorage.getItem('lmai_inspector_profile');
        if (saved) setProfile(JSON.parse(saved));
      } catch (_) {}
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const getStatusDisplay = () => {
    switch (healthState) {
      case 'ONLINE':
        return { dotClass: 'status-dot--online', text: 'Engine Online (v1.0)' };
      case 'DEGRADED':
        return { dotClass: 'status-dot--degraded', text: 'Engine Degraded' };
      case 'OFFLINE':
        return { dotClass: 'status-dot--offline', text: 'Backend Disconnected' };
      default:
        return { dotClass: 'status-dot--unknown', text: 'Checking Engine...' };
    }
  };

  const status = getStatusDisplay();

  return (
    <aside className="app-sidebar" aria-label="Inspection System Navigation">
      {/* Brand Header */}
      <div className="sidebar-brand">
        <NavLink to="/dashboard" onClick={onCloseMobile} className="sidebar-brand__link">
          <BrandLogo
            variant="dark"
            height={36}
            alt="LMAI Inspector"
            className="sidebar-brand__logo"
          />
        </NavLink>
        <div className="sidebar-brand__badge">
          <ShieldCheck size={12} className="text-teal" />
          <span>AI COMPLIANCE SCREENING</span>
        </div>
      </div>

      {/* Main Navigation Links */}
      <nav className="sidebar-nav">
        <div className="sidebar-nav__label">Inspection Modules</div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onCloseMobile}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? 'sidebar-link--active' : ''} ${
                  item.highlight ? 'sidebar-link--highlight' : ''
                }`
              }
            >
              <Icon size={18} className="sidebar-link__icon" />
              <span className="sidebar-link__text">{item.label}</span>
              {item.highlight && <span className="sidebar-link__pill">Scan</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Footer / Identity Area */}
      <div className="sidebar-footer">
        <div className="inspector-identity">
          <div className="inspector-identity__avatar">
            <UserCheck size={16} />
          </div>
          <div className="inspector-identity__meta">
            <span className="inspector-name">{profile.name || 'Workspace User'}</span>
            <span className="inspector-role">
              {profile.badge && profile.badge !== 'Not configured' ? `ID: ${profile.badge}` : 'ID: Not configured'} • {profile.station || 'Local'}
            </span>
          </div>
        </div>

        <div className="system-status-indicator">
          <div className={`status-dot ${status.dotClass}`} />
          <span className="status-text">{status.text}</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
