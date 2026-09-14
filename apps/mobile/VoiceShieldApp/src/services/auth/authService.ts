import AsyncStorage from '@react-native-async-storage/async-storage';
import client from '../api/client';
import { AuthTokens, UserProfile } from '../../types';

export const authService = {
  async login(email: string, password: string): Promise<AuthTokens> {
    const { data } = await client.post<AuthTokens>('/auth/login', { email, password });
    await AsyncStorage.setItem('access_token', data.access_token);
    await AsyncStorage.setItem('refresh_token', data.refresh_token);
    return data;
  },

  async register(email: string, password: string, full_name: string): Promise<AuthTokens> {
    const { data } = await client.post<AuthTokens>('/auth/register', { email, password, full_name });
    await AsyncStorage.setItem('access_token', data.access_token);
    await AsyncStorage.setItem('refresh_token', data.refresh_token);
    return data;
  },

  async logout(): Promise<void> {
    await AsyncStorage.removeItem('access_token');
    await AsyncStorage.removeItem('refresh_token');
  },

  async getMe(): Promise<UserProfile> {
    const { data } = await client.get<UserProfile>('/users/me');
    return data;
  },

  async hasValidToken(): Promise<boolean> {
    const token = await AsyncStorage.getItem('access_token');
    return !!token;
  },
};
