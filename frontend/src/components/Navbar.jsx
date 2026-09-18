import { Link, useLocation } from 'react-router-dom';
import { ShieldCheck, BarChart2, Clock, Info, Camera } from 'lucide-react';
import BrandLogo from './BrandLogo';
import './Navbar.css';

const Navbar = () => {
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Home', icon: <ShieldCheck size={18} /> },
    { path: '/dashboard', label: 'Dashboard', icon: <BarChart2 size={18} /> },
    { path: '/scan', label: 'New Scan', icon: <Camera size={18} /> },
    { path: '/history', label: 'History', icon: <Clock size={18} /> },
    { path: '/about', label: 'About', icon: <Info size={18} /> },
  ];

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand-link" title="LMAI Inspector Home">
        {/* Desktop Logo */}
        <BrandLogo
          variant="horizontal"
          className="navbar-logo navbar-logo--desktop"
          height={38}
          alt="LMAI Inspector"
        />
        {/* Mobile Compact Mark */}
        <BrandLogo
          variant="mark"
          className="navbar-logo navbar-logo--mobile"
          height={34}
          alt="LMAI Inspector"
        />
        <span className="navbar-mobile-title">LMAI</span>
      </Link>
      <div className="navbar-menu">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
          >
            {item.icon}
            <span>{item.label}</span>
          </Link>
        ))}
      </div>
      <div className="navbar-user">
        <div className="avatar">IN</div>
        <span>Inspector</span>
      </div>
    </nav>
  );
};

export default Navbar;
