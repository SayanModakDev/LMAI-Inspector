import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
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

  const getStatusBadge = (status) => {
    const s = (status || '').replace('-', '_');
    switch (s) {
      case 'COMPLIANT':
        return <span className="badge badge-success">1 — COMPLIANT</span>;
      case 'NON_COMPLIANT':
        return <span className="badge badge-danger">0 — NON-COMPLIANT</span>;
      case 'NOT_VERIFIABLE':
      case 'NEEDS_REVIEW':
        return <span className="badge badge-warning">REVIEW</span>;
      case 'NOT_APPLICABLE':
        return <span className="badge badge-gray">N/A</span>;
      default:
        return <span className="badge badge-gray">{status}</span>;
    }
  };

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
          <div className="stat-label">1 — COMPLIANT</div>
        </div>
        
        <div className="card stat-card border-danger">
          <div className="stat-value text-danger">{stats.non_compliant}</div>
          <div className="stat-label">0 — NON-COMPLIANT</div>
        </div>
        
        <div className="card stat-card border-warning">
          <div className="stat-value text-warning">{stats.not_verifiable}</div>
          <div className="stat-label">REVIEW — NEEDS EVIDENCE</div>
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

      {stats.recent_inspections && stats.recent_inspections.length > 0 && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <div className="card-header flex-between">
            <span>Recent Inspections</span>
            <Link to="/history" className="text-primary text-sm">View All History →</Link>
          </div>
          <div className="card-body p-0">
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Product</th>
                    <th>Category</th>
                    <th>Package Type</th>
                    <th>Import Status</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_inspections.map((item) => (
                    <tr key={item.id}>
                      <td>#{item.id}</td>
                      <td className="font-medium">{item.product_name || 'Not detected'}</td>
                      <td>{item.category}</td>
                      <td>{item.package_type || 'RETAIL'}</td>
                      <td>{item.import_status || 'DOMESTIC'}</td>
                      <td>{getStatusBadge(item.result)}</td>
                      <td>
                        <Link to={`/result/${item.id}`} className="btn btn-sm btn-outline">
                          View
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
