import { describe, expect, it } from 'vitest';

import { modalAnimationType } from '../motion';

describe('motion accessibility', () => {
  it('disables sheet motion when Reduce Motion is enabled', () => {
    expect(modalAnimationType(true)).toBe('none');
    expect(modalAnimationType(false)).toBe('slide');
  });
});
