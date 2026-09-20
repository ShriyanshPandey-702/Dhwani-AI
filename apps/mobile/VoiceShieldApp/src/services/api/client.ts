import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE_URL } from '../../config/api';
import { getApiBaseUrl } from '../../store/connectionStore';

const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor: dynamic baseURL and attach access token if present ──
client.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const dynamicBaseUrl = getApiBaseUrl();
  if (!dynamicBaseUrl) {
    return Promise.reject(
      new Error("Backend host not configured. Please set your Mac's LAN IP in Settings.")
    );
  }
  config.baseURL = dynamicBaseUrl;

  const token = await AsyncStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function analyzeAudioFile(formData: FormData): Promise<any> {
  const response = await client.post('/analysis/audio', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return response.data;
}

export default client;
