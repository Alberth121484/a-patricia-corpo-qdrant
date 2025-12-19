import axios from 'axios';

const API_BASE = '/api';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Decryption function (simple base64 + JSON for demo)
// In production, implement proper decryption matching backend
async function decryptResponse(encryptedData) {
  try {
    // Call backend to decrypt
    const response = await api.post('/decrypt', { data: encryptedData });
    return response.data;
  } catch (error) {
    console.error('Decryption error:', error);
    // Fallback: try to parse as plain JSON
    try {
      return JSON.parse(atob(encryptedData));
    } catch {
      return encryptedData;
    }
  }
}

// Auth API
export const authApi = {
  login: async (username, password) => {
    const response = await api.post('/auth/login', { username, password });
    return response.data;
  },
  
  getMe: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },
};

// Files API
export const filesApi = {
  upload: async (file, tiendaId, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    if (tiendaId) {
      formData.append('tienda_id', tiendaId);
    }
    
    const response = await api.post('/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    
    return decryptResponse(response.data.data);
  },
  
  list: async () => {
    const response = await api.get('/files');
    return decryptResponse(response.data.data);
  },
  
  get: async (fileId) => {
    const response = await api.get(`/files/${fileId}`);
    return decryptResponse(response.data.data);
  },
  
  delete: async (fileId) => {
    const response = await api.delete(`/files/${fileId}`);
    return decryptResponse(response.data.data);
  },
  
  preview: async (fileId, limit = 100) => {
    const response = await api.get(`/files/${fileId}/preview`, {
      params: { limit },
    });
    return decryptResponse(response.data.data);
  },
  
  getDownloadUrl: async (fileId) => {
    const response = await api.get(`/files/${fileId}/download`);
    return decryptResponse(response.data.data);
  },
};

// Stats API
export const statsApi = {
  get: async () => {
    const response = await api.get('/stats');
    return decryptResponse(response.data.data);
  },
};

export default api;
