import { describe, it, expect } from 'vitest';
import { formatBytes } from '../lib/format';
import { barColor } from '../lib/colors';

describe('formatBytes', () => {
  it('shows whole bytes below 1 KB', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(999)).toBe('999 B');
  });

  it('scales through KB, MB, GB, TB', () => {
    expect(formatBytes(1_500)).toBe('1.5 KB');
    expect(formatBytes(2_000_000)).toBe('2.0 MB');
    expect(formatBytes(3_200_000_000)).toBe('3.2 GB');
    expect(formatBytes(1_000_000_000_000)).toBe('1.0 TB');
  });

  it('caps at TB for very large values', () => {
    expect(formatBytes(5_000_000_000_000)).toBe('5.0 TB');
  });

  it('handles non-finite input', () => {
    expect(formatBytes(NaN)).toBe('0 B');
    expect(formatBytes(Infinity)).toBe('0 B');
  });
});

describe('barColor', () => {
  it('maps utilization to a severity class', () => {
    expect(barColor(0)).toBe('green');
    expect(barColor(50)).toBe('green');
    expect(barColor(50.1)).toBe('yellow');
    expect(barColor(80)).toBe('yellow');
    expect(barColor(80.1)).toBe('red');
    expect(barColor(100)).toBe('red');
  });
});
