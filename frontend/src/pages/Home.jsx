import { Link } from 'react-router-dom';
import { Camera, FileText, BarChart2 } from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import './Home.css';

const Home = () => {
  return (
    <div className="home-container">
      <div className="hero-section">
        <div className="hero-logo-wrapper">
          <BrandLogo
            variant="tagline"
            className="hero-brand-logo"
            alt="LMAI Inspector - Legal Metrology Packaged Commodities Compliance Screening"
          />
        </div>
        <p className="hero-subtitle">
          Automated label OCR and deterministic statutory validation for packaged commodity inspections under Legal Metrology (Packaged Commodities) Rules, 2011.
        </p>
        
        <div className="action-cards">
          <div className="action-card primary-action">
            <div className="action-icon-wrapper bg-blue">
              <Camera size={32} />
            </div>
            <h3>New Inspection</h3>
            <p>Scan a product label to automatically extract declarations and check compliance.</p>
            <Link to="/scan" className="btn btn-primary mt-auto">Start Scan</Link>
          </div>
          
          <div className="action-card">
            <div className="action-icon-wrapper bg-green">
              <FileText size={32} />
            </div>
            <h3>Inspection History</h3>
            <p>Review past inspections, manual verifications, and generated PDF reports.</p>
            <Link to="/history" className="btn btn-outline mt-auto">View History</Link>
          </div>
          
          <div className="action-card">
            <div className="action-icon-wrapper bg-purple">
              <BarChart2 size={32} />
            </div>
            <h3>Dashboard</h3>
            <p>View aggregate statistics and common non-compliance patterns across all scans.</p>
            <Link to="/dashboard" className="btn btn-outline mt-auto">View Dashboard</Link>
          </div>
        </div>
      </div>
      
      <div className="info-banner warning-banner">
        <strong>Important Disclaimer:</strong> This system is an inspection-support tool. 
        It does not provide automatic legal certification. Final verification must be made by the authorized inspector.
      </div>
    </div>
  );
};

export default Home;
