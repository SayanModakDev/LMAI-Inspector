import React, { useState } from 'react';
import {
  User,
  Activity,
  Scale,
  RefreshCw,
} from 'lucide-react';
import { useSystemHealth } from '../context/SystemHealthContext';
import { BRAND_CONFIG } from '../constants/branding';
import './Settings.css';

const Settings = () => {
  const { healthState, healthData, isChecking, refreshHealth } = useSystemHealth();

  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profile, setProfile] = useState(() => {
    try {
      const saved = localStorage.getItem('lmai_inspector_profile');
      if (saved) return JSON.parse(saved);
    } catch (_) {}
    return {
      name: 'Workspace User',
      badge: 'Not configured',
      station: 'Demo / Local Workspace',
      role: 'Screening Operator',
    };
  });
  const [profileForm, setProfileForm] = useState(profile);

  const handleSaveProfile = (e) => {
    e.preventDefault();
    setProfile(profileForm);
    localStorage.setItem('lmai_inspector_profile', JSON.stringify(profileForm));
    // Notify other components (Sidebar, Topbar)
    window.dispatchEvent(new Event('storage'));
    setIsEditingProfile(false);
  };

  const getHealthDotClass = () => {
    switch (healthState) {
      case 'ONLINE': return 'status-dot--online';
      case 'DEGRADED': return 'status-dot--degraded';
      case 'OFFLINE': return 'status-dot--offline';
      default: return 'status-dot--unknown';
    }
  };

  return (
    <div className="settings-page">
      {/* Header */}
      <div className="settings-header">
        <div>
          <h2 className="settings-title">Inspector Profile & Workstation Settings</h2>
          <p className="settings-subtitle">
            Configure local workstation identity, examine backend engine diagnostics, and review regulatory parameters.
          </p>
        </div>
      </div>

      <div className="settings-grid">
        {/* User / Inspector Profile Card */}
        <div className="card settings-card">
          <div className="card-header flex-between">
            <div className="flex items-center gap-2">
              <User size={18} className="text-primary" />
              <span>Inspector / Workstation Profile</span>
            </div>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => {
                if (!isEditingProfile) setProfileForm(profile);
                setIsEditingProfile(!isEditingProfile);
              }}
            >
              {isEditingProfile ? 'Cancel' : 'Edit Profile'}
            </button>
          </div>
          <div className="card-body">
            {isEditingProfile ? (
              <form onSubmit={handleSaveProfile} className="profile-edit-form">
                <div className="form-group mb-2">
                  <label className="form-label text-xs">Inspector / User Name</label>
                  <input
                    type="text"
                    className="form-control"
                    value={profileForm.name}
                    onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })}
                    placeholder="Enter name or identifier"
                    required
                  />
                </div>
                <div className="form-group mb-2">
                  <label className="form-label text-xs">Identifier / Ref ID</label>
                  <input
                    type="text"
                    className="form-control font-mono"
                    value={profileForm.badge}
                    onChange={(e) => setProfileForm({ ...profileForm, badge: e.target.value })}
                    placeholder="e.g. OP-104 or Not configured"
                    required
                  />
                </div>
                <div className="form-group mb-2">
                  <label className="form-label text-xs">Station / Workspace</label>
                  <input
                    type="text"
                    className="form-control"
                    value={profileForm.station}
                    onChange={(e) => setProfileForm({ ...profileForm, station: e.target.value })}
                    placeholder="e.g. Demo / Local Workspace"
                    required
                  />
                </div>
                <div className="form-group mb-3">
                  <label className="form-label text-xs">Role / Title</label>
                  <input
                    type="text"
                    className="form-control"
                    value={profileForm.role}
                    onChange={(e) => setProfileForm({ ...profileForm, role: e.target.value })}
                    placeholder="e.g. Screening Operator"
                    required
                  />
                </div>
                <button type="submit" className="btn btn-primary btn-sm">
                  Save Profile
                </button>
              </form>
            ) : (
              <div className="profile-detail-rows">
                <div className="profile-row">
                  <span className="p-label">Inspector / User:</span>
                  <span className="p-val font-semibold">{profile.name}</span>
                </div>
                <div className="profile-row">
                  <span className="p-label">Identifier / Ref ID:</span>
                  <span className="p-val font-mono">{profile.badge}</span>
                </div>
                <div className="profile-row">
                  <span className="p-label">Station / Workspace:</span>
                  <span className="p-val">{profile.station}</span>
                </div>
                <div className="profile-row">
                  <span className="p-label">Role / Title:</span>
                  <span className="p-val font-semibold text-primary">{profile.role}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Backend & Diagnostics Telemetry */}
        <div className="card settings-card">
          <div className="card-header flex-between">
            <div className="flex items-center gap-2">
              <Activity size={18} className="text-primary" />
              <span>Engine Diagnostics & Health</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn btn-outline btn-xs"
                onClick={refreshHealth}
                disabled={isChecking}
                title="Refresh engine telemetry"
              >
                <RefreshCw size={12} className={isChecking ? 'animate-spin' : ''} />
                <span>{isChecking ? 'Checking...' : 'Refresh'}</span>
              </button>
              <div className="flex items-center gap-1">
                <div className={`status-dot ${getHealthDotClass()}`} />
                <span className="text-xs font-mono font-semibold">
                  {healthState}
                </span>
              </div>
            </div>
          </div>
          <div className="card-body">
            <div className="profile-detail-rows">
              <div className="profile-row">
                <span className="p-label">Engine Application:</span>
                <span className="p-val font-semibold">{healthData?.app || 'LMAI Inspector'}</span>
              </div>
              <div className="profile-row">
                <span className="p-label">Engine Version:</span>
                <span className="p-val font-mono">{healthData?.version || 'v1.0.0'}</span>
              </div>
              <div className="profile-row">
                <span className="p-label">OCR Subsystem:</span>
                <span className="p-val">PaddleOCR Multi-Pass (Adaptive Preprocessing)</span>
              </div>
              <div className="profile-row">
                <span className="p-label">Barcode Decoder:</span>
                <span className="p-val">PyZbar / EAN-13 Checksum Engine</span>
              </div>
              <div className="profile-row">
                <span className="p-label">Persistence Database:</span>
                <span className="p-val">SQLite Local Enclave</span>
              </div>
            </div>
          </div>
        </div>

        {/* Regulatory Governance Framework */}
        <div className="card settings-card" style={{ gridColumn: '1 / -1' }}>
          <div className="card-header">
            <div className="flex items-center gap-2">
              <Scale size={18} className="text-primary" />
              <span>Governing Statutory Authorities & Standards</span>
            </div>
          </div>
          <div className="card-body">
            <div className="statutory-standards-grid">
              <div className="standard-item">
                <span className="standard-title">Legal Metrology Act, 2009</span>
                <span className="standard-desc">
                  Act No. 1 of 2010 — Establishes statutory standards of weights and measures and regulates trade in packaged commodities.
                </span>
              </div>
              <div className="standard-item">
                <span className="standard-title">{BRAND_CONFIG.legalStandard}</span>
                <span className="standard-desc">
                  G.S.R. 202(E) — Mandates mandatory printed declarations including MRP, Net Quantity, Dates, Manufacturer/Packer/Importer, and Consumer Care details.
                </span>
              </div>
              <div className="standard-item">
                <span className="standard-title">Advisory on AI Compliance Screening</span>
                <span className="standard-desc">
                  {BRAND_CONFIG.disclaimer}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
