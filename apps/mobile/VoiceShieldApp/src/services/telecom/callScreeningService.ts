import { NativeModules, NativeEventEmitter, Platform } from 'react-native';
import {
  CallScreeningRoleResult,
  ScreenedCallEvent,
} from '../../types/telecom';

function getNativeModule() {
  return NativeModules.VoiceShieldCallScreening;
}

class CallScreeningService {
  private _emitter: NativeEventEmitter | null = null;

  private get emitter(): NativeEventEmitter | null {
    if (!this._emitter && Platform.OS === 'android' && getNativeModule()) {
      this._emitter = new NativeEventEmitter(getNativeModule());
    }
    return this._emitter;
  }

  /**
   * Checks whether the app is currently granted the Android Call Screening role.
   */
  async isRoleHeld(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod) {
      return false;
    }
    return mod.isRoleHeld();
  }

  /**
   * Checks whether the Call Screening role is available on this Android device/version.
   */
  async getRoleAvailability(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod) {
      return false;
    }
    return mod.getRoleAvailability();
  }

  /**
   * Requests the user to designate VoiceShield as the Call Screening app.
   */
  async requestRole(): Promise<CallScreeningRoleResult> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod) {
      return { granted: false, alreadyHeld: false, error: 'PLATFORM_NOT_SUPPORTED' };
    }
    return mod.requestRole();
  }

  /**
   * Retrieves recent screened calls from persistent native storage.
   */
  async getRecentScreenedCalls(): Promise<ScreenedCallEvent[]> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod) {
      return [];
    }
    return mod.getRecentScreenedCalls();
  }

  /**
   * Clears the screened calls history from native storage.
   */
  async clearScreenedCalls(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod) {
      return true;
    }
    return mod.clearScreenedCalls();
  }

  /**
   * Listens for real-time screened call events emitted by the native service.
   */
  onCallScreened(listener: (event: ScreenedCallEvent) => void): () => void {
    const em = this.emitter;
    if (!em) {
      return () => {};
    }
    const subscription = em.addListener('onIncomingCallScreened', (event: any) => {
      listener(event as ScreenedCallEvent);
    });
    return () => subscription.remove();
  }

  /**
   * Listens for role status changes (e.g. granted or revoked by user in system settings).
   */
  onRoleStatusChanged(listener: (isHeld: boolean) => void): () => void {
    const em = this.emitter;
    if (!em) {
      return () => {};
    }
    const subscription = em.addListener('onRoleStatusChanged', (data: any) => {
      listener(Boolean(data?.isRoleHeld));
    });
    return () => subscription.remove();
  }
}

export const callScreeningService = new CallScreeningService();
