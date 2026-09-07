import React, { useEffect, useState } from 'react';
import {
  Settings as SettingsIcon,
  User,
  ShieldCheck,
  Cpu,
  Database,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Scale,
} from 'lucide-react';
import './Settings.css';

const Settings = () => {
  const [healthData, setHealthData] = useState(null);
  const [healthStatus, setHealthStatus] = useState('checking');

  useEffect(() => {
    fetch('/health')
      .then((res) => {
        if (!res.ok) throw new Error('Health check failed');
        return res.json();
      })
      .then((data) => {
        setHealthData(data);
        setHealthStatus('online');
      })
      .catch((err) => {
        console.error(err);
        setHealthStatus('offline');
      });
  }, []);

  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profile, setProfile] = useState(() => {
    try {
      const saved = localStorage.getItem('lmai_inspector_profile');
      if (saved) return JSON.parse(saved);
    } catch (_) {}
    return {
      name: 'Legal Metrology Officer',
      badge: 'IN-4029',
      jurisdiction: 'Regional Metrology Directorate (Zone 4)',
      role: 'Senior Inspecting Officer',
    };
  });
  const [profileForm, setProfileForm] = useState(profile);

  const handleSaveProfile = (e) => {
    e.preventDefault();
    setProfile(profileForm);
    localStorage.setItem('lmai_inspector_profile', JSON.stringify(profileForm));
    setIsEditingProfile(false);
  };

  return (
    <div className="settings-page">
      {/* Header */}
      <div className="settings-header">
        <div>
          <h2 className="settings-title">Inspector Profile & Workstation Settings</h2>
          <p className="settings-subtitle">
            Configure field officer credentials, examine backend engine diagnostics, and manage compliance parameters.
          </p>
        </div>
      </div>

      <div className="settings-grid">
        {/* Officer Profile Card */}
        <div className="card settings-card">
          <div className="card-header flex-between">
            <div className="flex items-center gap-2">
              <User size={18} className="text-primary" />
              <span>Inspector Credentials</span>
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
                  <label className="form-label text-xs">Officer Name</label>
                  <input
                    type="text"
                    className="form-control"
                    value={profileForm.name}
                    onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })}
                    placeholder="Enter officer name"
                    required
                  />
                </div>
                <div className="form-group mb-2">
                  <label className="form-label text-xs">Badge / Identifier</label>
                  <input
                    type="text"
                    className="form-control font-mono"
                    value={profileForm.badge}
                    onChange={(e) => setProfileForm({ ...profileForm, badge: e.target.value })}
                    placeholder="e.g. IN-4029"
                    required
                  />
                </div>
                <div className="form-group mb-2">
                  <label className="form-label text-xs">Jurisdiction / Zone</label>
                  <input
                    type="text"
                    className="form-control"
                    value={profileForm.jurisdiction}
                    onChange={(e) => setProfileForm({ ...profileForm, jurisdiction: e.target.value })}
                    placeholder="e.g. Regional Directorate"
                    required
                  />
                </div>
                <div className="form-group mb-3">
                  <label className="form-label text-xs">Authorization Role</label>
                  <input
                    type="text"
                    className="form-control"
                    value={profileForm.role}
                    onChange={(e) => setProfileForm({ ...profileForm, role: e.target.value })}
                    placeholder="e.g. Inspecting Officer"
                    required
                  />
                </div>
                <button type="submit" className="btn btn-primary btn-sm">
                  Save Credentials
                </button>
              </form>
            ) : (
              <div className="profile-detail-rows">
                <div className="profile-row">
                  <span className="p-label">Officer Name:</span>
                  <span className="p-val font-semibold">{profile.name}</span>
                </div>
                <div className="profile-row">
                  <span className="p-label">Badge / Identifier:</span>
                  <span className="p-val font-mono">{profile.badge}</span>
                </div>
                <div className="profile-row">
                  <span className="p-label">Jurisdiction / Zone:</span>
                  <span className="p-val">{profile.jurisdiction}</span>
                </div>
                <div className="profile-row">
                  <span className="p-label">Authorization Role:</span>
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
              <span>System & Engine Health</span>
            </div>
            <div className="flex items-center gap-1">
              <div className={`status-dot ${healthStatus === 'online' ? 'status-dot--online' : 'status-dot--offline'}`} />
              <span className="text-xs font-mono font-semibold">
                {healthStatus === 'online' ? 'ONLINE' : 'OFFLINE'}
              </span>
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
                <span className="p-val">PaddleOCR Multi-Pass (Preserved Fidelity)</span>
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
                <span className="standard-title">Packaged Commodities Rules, 2011</span>
                <span className="standard-desc">
                  G.S.R. 202(E) — Mandates mandatory printed declarations including MRP, Net Quantity, Dates, Manufacturer/Packer, and Consumer Care.
                </span>
              </div>
              <div className="standard-item">
                <span className="standard-title">Advisory on AI Screening</span>
                <span className="standard-desc">
                  LMAI Inspector operates exclusively as an officer-in-the-loop decision-support tool. Formal enforcement notices require officer sign-off.
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
