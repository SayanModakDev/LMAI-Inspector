import axios from 'axios';

// Base URL for the backend API, configurable via VITE_API_BASE_URL
const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim();
export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, '');

/**
 * Resolves a path or relative URL against the configured backend base URL.
 * If path is already absolute (http:// or https://), returns it unchanged.
 */
export const resolveBackendUrl = (path = '') => {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('blob:') || path.startsWith('data:')) {
    return path;
  }
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return API_BASE_URL ? `${API_BASE_URL}${cleanPath}` : cleanPath;
};

const api = axios.create({
  baseURL: API_BASE_URL ? `${API_BASE_URL}/api` : '/api',
});


export const apiService = {
  // Scan
  uploadScan: async (files, packageType = 'RETAIL', importStatus = 'DOMESTIC', onUploadProgress) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    formData.append('package_type', packageType);
    formData.append('import_status', importStatus);

    const response = await api.post('/scan', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress,
    });
    return response.data;
  },

  // Inspections
  getHistory: async (skip = 0, limit = 100, status, category) => {
    const params = { skip, limit, status, category };
    const response = await api.get('/history', { params });
    return response.data;
  },

  getInspection: async (id) => {
    const response = await api.get(`/inspection/${id}`);
    return response.data;
  },

  getDashboardStats: async () => {
    const response = await api.get('/dashboard');
    return response.data;
  },

  submitManualInput: async (data) => {
    const response = await api.post('/manual-input', data);
    return response.data;
  },

  // Reports
  generateReport: async (id) => {
    const response = await api.post(`/report/${id}`);
    return response.data;
  },

  // Metadata
  getCategories: async () => {
    const response = await api.get('/categories');
    return response.data;
  },

  getRules: async () => {
    const response = await api.get('/rules');
    return response.data;
  },
};
