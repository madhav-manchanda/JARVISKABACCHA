import React from 'react';
import { NavLink } from 'react-router-dom';
import { Terminal, Database, Users, Activity, LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Sidebar = () => {
  const { logout } = useAuth();

  const links = [
    { to: "/", icon: <Terminal className="w-5 h-5" />, label: "Command Hub" },
    { to: "/memory", icon: <Database className="w-5 h-5" />, label: "Memory Core" },
    { to: "/contacts", icon: <Users className="w-5 h-5" />, label: "Contacts" },
    { to: "/health", icon: <Activity className="w-5 h-5" />, label: "System Health" },
  ];

  return (
    <aside className="w-64 bg-jarvis-bgSecondary/80 backdrop-blur-md border-r border-white/10 h-screen flex flex-col pt-6 z-20">
      <div className="flex items-center gap-3 px-6 mb-10">
        <div className="w-10 h-10 rounded-full bg-jarvis-bg border border-jarvis-cyan/30 flex items-center justify-center shadow-[0_0_10px_rgba(0,242,254,0.2)]">
          <Terminal className="text-jarvis-cyan w-5 h-5" />
        </div>
        <h1 className="text-xl font-bold tracking-wider text-jarvis-textMain">JARVIS</h1>
      </div>

      <nav className="flex-1 px-4 space-y-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-all font-medium ${
                isActive 
                  ? 'bg-jarvis-cyan/10 text-jarvis-cyan border border-jarvis-cyan/20 shadow-[inset_0_0_10px_rgba(0,242,254,0.1)]' 
                  : 'text-jarvis-textMuted hover:bg-white/5 hover:text-jarvis-textMain'
              }`
            }
          >
            {link.icon}
            {link.label}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-white/10">
        <button 
          onClick={logout}
          className="flex items-center gap-3 px-4 py-3 w-full rounded-lg text-jarvis-alert hover:bg-jarvis-alert/10 transition-all font-medium"
        >
          <LogOut className="w-5 h-5" />
          Disconnect
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
