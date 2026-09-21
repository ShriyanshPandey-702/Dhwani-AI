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

  /**
   * Opens Android system settings for Default Apps / Call Screening role management.
   */
  async openCallScreeningSettings(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod?.openCallScreeningSettings) {
      return false;
    }
    return mod.openCallScreeningSettings();
  }

  /**
   * Gets a bundled demo audio sample as a real file:// URI.
   */
  async getDemoAudioSample(sampleType: 'synthetic' | 'benign' | 'short'): Promise<{ uri: string; name: string; type: string; size: number }> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod?.getDemoAudioSample) {
      throw new Error('Platform not supported for demo audio samples');
    }
    return mod.getDemoAudioSample(sampleType);
  }

  /**
   * Prompts user to pick an audio file from local storage using Android's document picker.
   */
  async pickAudioFile(): Promise<{ uri: string; name: string; type: string; size: number } | null> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod?.pickAudioFile) {
      throw new Error('Platform not supported for picking audio files');
    }
    return mod.pickAudioFile();
  }

  /**
   * Triggers a local-only test notification to verify channel, priority, and permissions.
   * Creates NO call/session/risk records and affects NO statistics.
   */
  async testSecurityNotification(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod?.testSecurityNotification) {
      return false;
    }
    return mod.testSecurityNotification();
  }

  /**
   * Checks whether READ_CONTACTS permission is currently granted.
   * READ_CONTACTS is needed for Android Telecom to pass contact calls to CallScreeningService.
   */
  async hasContactsPermission(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod?.hasContactsPermission) {
      return false;
    }
    return mod.hasContactsPermission();
  }

  /**
   * Checks current contacts permission state.
   * Note: READ_CONTACTS is declared in the manifest and granted at install time.
   * If not granted, the user must go to App Settings → Permissions → Contacts.
   */
  async requestContactsPermission(): Promise<boolean> {
    const mod = getNativeModule();
    if (Platform.OS !== 'android' || !mod?.requestContactsPermission) {
      return false;
    }
    return mod.requestContactsPermission();
  }
}

export const callScreeningService = new CallScreeningService();
