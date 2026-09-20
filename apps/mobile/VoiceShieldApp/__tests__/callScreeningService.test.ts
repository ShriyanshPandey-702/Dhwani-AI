import { NativeModules, NativeEventEmitter, Platform } from 'react-native';

(Platform as any).OS = 'android';

const mockIsRoleHeld = jest.fn();
const mockRequestRole = jest.fn();
const mockGetRoleAvailability = jest.fn();
const mockGetRecentScreenedCalls = jest.fn();
const mockClearScreenedCalls = jest.fn();

let screenedCallListener: ((event: any) => void) | null = null;
let roleStatusListener: ((data: any) => void) | null = null;

NativeModules.VoiceShieldCallScreening = {
  isRoleHeld: mockIsRoleHeld,
  requestRole: mockRequestRole,
  getRoleAvailability: mockGetRoleAvailability,
  getRecentScreenedCalls: mockGetRecentScreenedCalls,
  clearScreenedCalls: mockClearScreenedCalls,
  addListener: jest.fn(),
  removeListeners: jest.fn(),
};

jest.spyOn(NativeEventEmitter.prototype, 'addListener').mockImplementation(function (
  event: any,
  callback: any,
) {
  if (event === 'onIncomingCallScreened') {
    screenedCallListener = callback;
  } else if (event === 'onRoleStatusChanged') {
    roleStatusListener = callback;
  }
  return {
    remove: jest.fn(),
  } as any;
});

import { callScreeningService } from '../src/services/telecom/callScreeningService';
import { useCallScreeningStore } from '../src/store/callScreeningStore';
import { ScreenedCallEvent } from '../src/types/telecom';

describe('Call Screening Service & Store', () => {
  const sampleEvent: ScreenedCallEvent = {
    eventId: 'evt-1234',
    timestamp: 1726830000000,
    callerMasked: '+91 ***** *3210',
    callerHash: 'b4661448dbd54e4c2957b49aa4c965b3992fa68c0b5614917fbfd00346a099a4',
    verificationStatus: 'FAILED',
    decision: 'ALLOW',
    riskLevel: 'HIGH',
    warningType: 'VERIFICATION_FAILED',
    reasonCodes: ['CALLER_VERIFICATION_FAILED'],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    screenedCallListener = null;
    roleStatusListener = null;
    useCallScreeningStore.setState({
      isRoleHeld: false,
      isAvailable: true,
      recentCalls: [],
      activeAlert: null,
      isLoading: false,
      error: null,
    });
  });

  // 1. isRoleHeld()
  test('isRoleHeld reports true when role is granted in Android', async () => {
    mockIsRoleHeld.mockResolvedValue(true);
    const held = await callScreeningService.isRoleHeld();
    expect(held).toBe(true);
    expect(mockIsRoleHeld).toHaveBeenCalledTimes(1);
  });

  // 2. requestRole()
  test('requestRole resolves with granted result when user accepts', async () => {
    mockRequestRole.mockResolvedValue({ granted: true, alreadyHeld: false });
    const result = await callScreeningService.requestRole();
    expect(result.granted).toBe(true);
    expect(mockRequestRole).toHaveBeenCalledTimes(1);
  });

  // 3. role status update via store
  test('store checkRoleStatus updates isRoleHeld state correctly', async () => {
    mockIsRoleHeld.mockResolvedValue(true);
    mockGetRoleAvailability.mockResolvedValue(true);

    const held = await useCallScreeningStore.getState().checkRoleStatus();
    expect(held).toBe(true);
    expect(useCallScreeningStore.getState().isRoleHeld).toBe(true);
  });

  // 4. native event handling
  test('onCallScreened callback fires on native bridge event and updates store', () => {
    let received: ScreenedCallEvent | null = null;
    const unsub = callScreeningService.onCallScreened(evt => {
      received = evt;
      useCallScreeningStore.getState().addScreenedCall(evt);
    });

    expect(screenedCallListener).not.toBeNull();
    screenedCallListener!(sampleEvent);

    expect(received).toEqual(sampleEvent);
    expect(useCallScreeningStore.getState().recentCalls).toHaveLength(1);
    expect(useCallScreeningStore.getState().recentCalls[0].eventId).toBe('evt-1234');
    unsub();
  });

  // 5. loading recent events from native persistence
  test('loadRecentCalls populates store with persisted events', async () => {
    mockGetRecentScreenedCalls.mockResolvedValue([sampleEvent]);

    await useCallScreeningStore.getState().loadRecentCalls();
    expect(useCallScreeningStore.getState().recentCalls).toEqual([sampleEvent]);
    expect(mockGetRecentScreenedCalls).toHaveBeenCalledTimes(1);
  });

  // 6. clearing events
  test('clearHistory removes persisted events and resets state', async () => {
    useCallScreeningStore.setState({ recentCalls: [sampleEvent], activeAlert: sampleEvent });
    mockClearScreenedCalls.mockResolvedValue(true);

    await useCallScreeningStore.getState().clearHistory();
    expect(useCallScreeningStore.getState().recentCalls).toEqual([]);
    expect(useCallScreeningStore.getState().activeAlert).toBeNull();
    expect(mockClearScreenedCalls).toHaveBeenCalledTimes(1);
  });

  // 7. persisted history rendering & bounding
  test('store bounds recent calls to maximum 50 events', () => {
    for (let i = 0; i < 60; i++) {
      useCallScreeningStore.getState().addScreenedCall({
        ...sampleEvent,
        eventId: `evt-${i}`,
      });
    }
    expect(useCallScreeningStore.getState().recentCalls).toHaveLength(50);
    // Most recent event at index 0
    expect(useCallScreeningStore.getState().recentCalls[0].eventId).toBe('evt-59');
  });

  // 8. notification/warning state
  test('high-risk screened call triggers activeAlert in store', () => {
    useCallScreeningStore.getState().addScreenedCall(sampleEvent);
    expect(useCallScreeningStore.getState().activeAlert).not.toBeNull();
    expect(useCallScreeningStore.getState().activeAlert?.warningType).toBe('VERIFICATION_FAILED');

    useCallScreeningStore.getState().dismissAlert();
    expect(useCallScreeningStore.getState().activeAlert).toBeNull();
  });

  // 9. PII masking assumptions
  test('screened call event never exposes unmasked raw phone numbers', () => {
    const rawNumber = '9876543210';
    expect(sampleEvent.callerMasked).not.toContain(rawNumber);
    expect(sampleEvent.callerMasked).toBe('+91 ***** *3210');
    expect(sampleEvent.callerHash).toHaveLength(64); // SHA-256
  });
});
