// VoiceShield API Configuration
// Using localhost:8000 works seamlessly via 'adb reverse tcp:8000 tcp:8000'
export const API_BASE_URL = 'http://localhost:8000';
export const WS_BASE_URL  = 'ws://localhost:8000';

// Fallbacks if not using adb reverse:
// export const API_BASE_URL = 'http://10.0.2.2:8000';  // Android emulator
// export const WS_BASE_URL  = 'ws://10.0.2.2:8000';
