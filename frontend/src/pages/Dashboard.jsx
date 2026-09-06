import { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import './Dashboard.css';

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await apiService.getDashboardStats();
        setStats(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) return <div className="p-4">Loading dashboard...</div>;
  if (!stats) return <div className="p-4">Failed to load stats.</div>;

  return (
    <div className="dashboard-container">
      <h1 className="mb-4">Compliance Dashboard</h1>
      
      <div className="stat-cards">
        <div className="card stat-card">
          <div className="stat-value">{stats.total_inspections}</div>
          <div className="stat-label">Total Inspections</div>
        </div>
        
        <div className="card stat-card border-success">
          <div className="stat-value text-success">{stats.compliant}</div>
          <div className="stat-label">Compliant</div>
        </div>
        
        <div className="card stat-card border-danger">
          <div className="stat-value text-danger">{stats.non_compliant}</div>
          <div className="stat-label">Non-Compliant</div>
        </div>
        
        <div className="card stat-card border-warning">
          <div className="stat-value text-warning">{stats.not_verifiable}</div>
          <div className="stat-label">Needs Review</div>
        </div>
      </div>
      
      <div className="dashboard-grid">
        <div className="card">
          <div className="card-header">Common Non-Compliance Issues</div>
          <div className="card-body p-0">
            <table className="rule-table">
              <thead>
                <tr>
                  <th>Rule Parameter</th>
                  <th>Failures</th>
                </tr>
              </thead>
              <tbody>
                {stats.common_failed_parameters.map((fail, i) => (
                  <tr key={i}>
                    <td className="font-medium">{fail.parameter}</td>
                    <td><span className="badge badge-danger">{fail.count}</span></td>
                  </tr>
                ))}
                {stats.common_failed_parameters.length === 0 && (
                  <tr><td colSpan="2">No failure data available.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        
        <div className="card">
          <div className="card-header">Inspections by Category</div>
          <div className="card-body p-0">
            <table className="rule-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Food</td>
                  <td>{stats.food_inspections}</td>
                </tr>
                <tr>
                  <td>Cosmetic</td>
                  <td>{stats.cosmetic_inspections}</td>
                  </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
