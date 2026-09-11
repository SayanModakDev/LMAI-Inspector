import React from 'react';
import { Link } from 'react-router-dom';
import BrandLogo from './BrandLogo';
import { BRAND_CONFIG } from '../constants/branding';
import './Footer.css';

const Footer = () => {
  return (
    <footer className="footer-container">
      <div className="footer-content">
        <div className="footer-brand-col">
          <Link to="/" className="footer-brand-link">
            <BrandLogo variant="dark" height={36} alt={BRAND_CONFIG.name} />
          </Link>
          <p className="footer-tagline">
            {BRAND_CONFIG.tagline} • {BRAND_CONFIG.subTagline}
          </p>
          <p className="footer-disclaimer">
            {BRAND_CONFIG.disclaimer}
          </p>
        </div>

        <div className="footer-links-col">
          <h4 className="footer-heading">Navigation</h4>
          <ul className="footer-nav-list">
            <li><Link to="/">Home</Link></li>
            <li><Link to="/scan">New Scan</Link></li>
            <li><Link to="/dashboard">Analytics Dashboard</Link></li>
            <li><Link to="/history">Inspection History</Link></li>
            <li><Link to="/about">System Documentation</Link></li>
          </ul>
        </div>

        <div className="footer-standards-col">
          <h4 className="footer-heading">Compliance Framework</h4>
          <ul className="footer-standards-list">
            <li>Legal Metrology Act, 2009</li>
            <li>Legal Metrology (Packaged Commodities) Rules, 2011</li>
            <li>Mandatory Statutory Declarations (MRP, Net Qty, Dates)</li>
            <li>Deterministic Rule Verification Engine</li>
          </ul>
        </div>
      </div>

      <div className="footer-bottom">
        <div className="footer-bottom-inner">
          <p className="footer-copyright">
            © {new Date().getFullYear()} {BRAND_CONFIG.name}. Built for Legal Metrology compliance screening.
          </p>
          <div className="footer-badges">
            <span className="footer-badge">v1.0 Production</span>
            <span className="footer-badge">Legal Metrology (PC) Rules, 2011</span>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
