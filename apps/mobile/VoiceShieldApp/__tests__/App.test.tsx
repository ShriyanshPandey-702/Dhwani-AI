/**
 * App smoke test — the root renders and shows the splash before the navigator.
 *
 * The API client is mocked so nothing reaches the network, and timers are faked
 * so the splash's animation and hand-off do not outlive the test environment.
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import { Text } from 'react-native';

jest.mock('../src/services/api/client', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockRejectedValue(new Error('offline in tests')),
    post: jest.fn().mockRejectedValue(new Error('offline in tests')),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  },
}));

import App from '../App';

describe('App', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  it('mounts and shows the splash screen', async () => {
    let tree!: ReactTestRenderer.ReactTestRenderer;

    await ReactTestRenderer.act(async () => {
      tree = ReactTestRenderer.create(<App />);
    });

    const text = tree.root
      .findAllByType(Text)
      .flatMap(node =>
        React.Children.toArray(node.props.children).filter(
          (c): c is string => typeof c === 'string',
        ),
      )
      .join(' ');

    expect(text).toContain('VoiceShield');

    await ReactTestRenderer.act(async () => {
      tree.unmount();
    });
  });
});
