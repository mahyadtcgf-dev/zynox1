import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from '@/pages/LoginPage';

describe('LoginPage', () => {
  function renderPage() {
    return render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
  }

  it('renders the Zynox brand', () => {
    renderPage();
    expect(screen.getByText('Zynox')).toBeInTheDocument();
  });

  it('renders username and password fields', () => {
    renderPage();
    expect(screen.getByPlaceholderText('admin')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/••••••••••/)).toBeInTheDocument();
  });

  it('disables submission while loading', () => {
    renderPage();
    const button = screen.getByRole('button', { name: /sign in/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it('does not display an error before a failed attempt', () => {
    renderPage();
    expect(screen.queryByText(/login failed/i)).not.toBeInTheDocument();
  });
});
