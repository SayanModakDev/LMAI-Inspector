import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Eye, Download, FileText } from 'lucide-react';
import { apiService } from '../services/api';

const History = () => {
  const [inspections, setInspections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('ALL');

  useEffect(() => {
    fetchHistory();
  }, [filter]);

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const status = filter !== 'ALL' ? filter : undefined;
      const data = await apiService.getHistory(0, 50, status);
      setInspections(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

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

  return (
    <div>
      <div className="flex-between mb-4">
        <h1>Inspection History</h1>
        <div className="flex gap-2">
          <select 
            className="form-control" 
            value={filter} 
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: 'auto' }}
          >
            <option value="ALL">All Statuses</option>
            <option value="COMPLIANT">1 — Compliant</option>
            <option value="NON_COMPLIANT">0 — Non-Compliant</option>
            <option value="NOT_VERIFIABLE">REVIEW — Needs Evidence</option>
            <option value="NOT_APPLICABLE">N/A — Not Applicable</option>
          </select>
          <Link to="/scan" className="btn btn-primary">New Scan</Link>
        </div>
      </div>

      <div className="card">
        <div className="card-body p-0">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Date</th>
                  <th>Category</th>
                  <th>Package Type</th>
                  <th>Import Status</th>
                  <th>Status</th>
                  <th>Report</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="8" className="text-center p-4">Loading...</td></tr>
                ) : inspections.length === 0 ? (
                  <tr><td colSpan="8" className="text-center p-4">No records found.</td></tr>
                ) : (
                  inspections.map((item) => (
                    <tr key={item.id}>
                      <td>#{item.id}</td>
                      <td>{new Date(item.created_at).toLocaleDateString()} {new Date(item.created_at).toLocaleTimeString()}</td>
                      <td>{item.category}</td>
                      <td>
                        <div className="font-medium">{item.package_type || 'RETAIL'}</div>
                        <div className="text-xs text-muted" style={{ fontSize: '0.7rem' }}>
                          {item.package_type === 'RETAIL' ? 'Inspector Default' : 'Inspector Selected'}
                        </div>
                      </td>
                      <td>
                        <div className="font-medium">{item.import_status || 'DOMESTIC'}</div>
                        <div className="text-xs text-muted" style={{ fontSize: '0.7rem' }}>
                          {item.import_status === 'DOMESTIC' ? 'Inspector Default' : 'Inspector Selected'}
                        </div>
                      </td>
                      <td>{getStatusBadge(item.overall_result)}</td>
                      <td>
                        {item.report ? (
                          <a href={`/api/report/${item.id}/download`} target="_blank" rel="noreferrer" className="text-primary flex align-center gap-1">
                            <FileText size={14} /> PDF
                          </a>
                        ) : (
                          <span className="text-muted text-sm">Not generated</span>
                        )}
                      </td>
                      <td>
                        <Link to={`/result/${item.id}`} className="btn btn-sm btn-outline">
                          <Eye size={14} /> View
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default History;
