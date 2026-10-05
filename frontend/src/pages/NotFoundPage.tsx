import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';
import { AppLayout } from '@/layouts/AppLayout';
import { Button } from '@/components/ui/Button';

export function NotFoundPage() {
  return (
    <AppLayout>
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="font-mono text-6xl font-semibold text-base-600">404</p>
        <h1 className="mt-4 text-lg font-semibold text-slate-100">Page not found</h1>
        <p className="mt-1.5 text-sm text-muted">The page you are looking for does not exist.</p>
        <Link to="/dashboard" className="mt-6">
          <Button variant="primary">
            <Home className="h-4 w-4" />
            Back to dashboard
          </Button>
        </Link>
      </div>
    </AppLayout>
  );
}
