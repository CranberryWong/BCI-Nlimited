import axios from 'axios';

export const api = axios.create({ baseURL: '/api' });

export async function downloadConfig() {
  const response = await api.get('/music/config/export', { responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'music-config.yaml';
  link.click();
  URL.revokeObjectURL(url);
}
