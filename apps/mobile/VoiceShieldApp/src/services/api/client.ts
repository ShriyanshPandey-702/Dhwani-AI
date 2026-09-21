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

/**
 * Robustly formats API errors into user-actionable messages.
 * Handles timeouts, offline backend, HTTP 400/413/422/500 without crashing.
 */
export function formatApiError(err: any): string {
  if (!err) {
    return 'An unexpected error occurred';
  }

  // HTTP Response error from backend
  if (err.response) {
    const status = err.response.status;
    const data = err.response.data;
    const detailMsg = data?.detail?.message || data?.detail;

    if (status === 400) {
      return detailMsg || 'Invalid request or audio format.';
    }
    if (status === 413) {
      return detailMsg || 'File is too large (maximum size is 25 MB).';
    }
    if (status === 422) {
      return 'Validation error: The audio submission format or parameters are invalid.';
    }
    if (status === 500) {
      return 'VoiceShield backend server error during analysis. Check server logs.';
    }
    if (detailMsg) {
      return detailMsg;
    }
  }

  // Network or connection errors
  if (err.code === 'ECONNABORTED' || err.message?.toLowerCase().includes('timeout')) {
    return 'Request timed out. The server took too long to analyze the audio.';
  }

  if (
    err.message === 'Network Error' ||
    err.code === 'ERR_NETWORK' ||
    err.code === 'ECONNREFUSED' ||
    err.message?.includes('Network request failed')
  ) {
    return 'VoiceShield backend is not running.\nStart FastAPI on port 8000 and try again.';
  }

  return err.message || 'An unexpected error occurred during analysis.';
}

export default client;
