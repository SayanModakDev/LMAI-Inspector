import React from 'react';
import { Routes, Route } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import Home from './pages/Home';
import Dashboard from './pages/Dashboard';
import Scan from './pages/Scan';
import Processing from './pages/Processing';
import Result from './pages/Result';
import History from './pages/History';
import RuleMatrix from './pages/RuleMatrix';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import About from './pages/About';

import { SystemHealthProvider } from './context/SystemHealthContext';

function App() {
  return (
    <SystemHealthProvider>
      <AppLayout>
        <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/home" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/scan" element={<Scan />} />
        <Route path="/processing" element={<Processing />} />
        <Route path="/result/:inspection_id" element={<Result />} />
        <Route path="/history" element={<History />} />
        <Route path="/rules" element={<RuleMatrix />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/about" element={<About />} />
      </Routes>
      </AppLayout>
    </SystemHealthProvider>
  );
}

export default App;
