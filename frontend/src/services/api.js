import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
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
