import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IntentInput } from '../components/Sentinel/IntentInput';

describe('IntentInput', () => {
  it('renders input and button', () => {
    render(<IntentInput onSend={() => {}} />);
    expect(screen.getByPlaceholderText('What do you want to do?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /go/i })).toBeInTheDocument();
  });

  it('button is disabled when input is empty', () => {
    render(<IntentInput onSend={() => {}} />);
    expect(screen.getByRole('button', { name: /go/i })).toBeDisabled();
  });

  it('button is disabled when disabled prop is true', () => {
    render(<IntentInput onSend={() => {}} disabled />);
    expect(screen.getByRole('button', { name: /processing/i })).toBeDisabled();
  });

  it('shows custom placeholder', () => {
    render(<IntentInput onSend={() => {}} placeholder="test prompt" />);
    expect(screen.getByPlaceholderText('test prompt')).toBeInTheDocument();
  });
});
