import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageCircle, Heart, Stethoscope } from 'lucide-react';

export default function Layout() {
  const location = useLocation();
  const isNurseView = location.pathname.startsWith('/dashboard') || location.pathname.startsWith('/patient');

  const navItems = isNurseView
    ? [
        { to: '/dashboard', icon: LayoutDashboard, label: 'Worklist' },
        { to: '/chat', icon: MessageCircle, label: 'Patient Chat' },
      ]
    : [
        { to: '/chat', icon: MessageCircle, label: 'Chat' },
        { to: '/dashboard', icon: Stethoscope, label: 'Nurse Dashboard' },
      ];

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-16 bg-white border-r border-slate-200 flex flex-col items-center py-4 gap-2">
        <div className="w-10 h-10 rounded-xl bg-teal-600 flex items-center justify-center mb-6">
          <Heart className="w-5 h-5 text-white" strokeWidth={2.5} />
        </div>

        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${
                isActive
                  ? 'bg-teal-50 text-teal-700'
                  : 'text-slate-400 hover:bg-slate-50 hover:text-slate-600'
              }`
            }
            title={label}
          >
            <Icon className="w-5 h-5" />
          </NavLink>
        ))}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
