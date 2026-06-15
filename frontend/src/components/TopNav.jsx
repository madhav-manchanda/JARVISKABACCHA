import React from 'react';
import { NavLink } from 'react-router-dom';
import { Terminal, BookOpen, LogOut, PenTool } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const TopNav = () => {
  const { logout } = useAuth();

  return (
    <header className="h-16 bg-jarvis-bgSecondary/80 backdrop-blur-md border-b border-white/10 flex items-center justify-between px-6 z-30 sticky top-0">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-jarvis-bg border border-jarvis-primary/30 flex items-center justify-center shadow-[0_0_15px_rgba(168,85,247,0.3)]">
          <Terminal className="text-jarvis-primary w-4 h-4" />
        </div>
        <h1 className="text-lg font-bold tracking-wider text-white font-montserrat">JARVIS</h1>
      </div>

      <nav className="flex items-center gap-6">
        <NavLink
          to="/"
          className={({ isActive }) =>
            `flex items-center gap-2 text-sm font-medium transition-colors ${
              isActive ? 'text-jarvis-primary drop-shadow-[0_0_8px_rgba(168,85,247,0.5)]' : 'text-jarvis-textMuted hover:text-white'
            }`
          }
        >
          <Terminal className="w-4 h-4" />
          Command Hub
        </NavLink>
        <NavLink
          to="/guide"
          className={({ isActive }) =>
            `flex items-center gap-2 text-sm font-medium transition-colors ${
              isActive ? 'text-jarvis-primary drop-shadow-[0_0_8px_rgba(168,85,247,0.5)]' : 'text-jarvis-textMuted hover:text-white'
            }`
          }
        >
          <BookOpen className="w-4 h-4" />
          User Guide
        </NavLink>
        <NavLink
          to="/homework"
          className={({ isActive }) =>
            `flex items-center gap-2 text-sm font-medium transition-colors ${
              isActive ? 'text-jarvis-primary drop-shadow-[0_0_8px_rgba(168,85,247,0.5)]' : 'text-jarvis-textMuted hover:text-white'
            }`
          }
        >
          <PenTool className="w-4 h-4" />
          Homework
        </NavLink>
        
        <div className="w-px h-5 bg-white/10 mx-2" />
        
        <button 
          onClick={logout}
          className="flex items-center gap-2 text-sm font-medium text-jarvis-alert hover:text-red-400 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Disconnect
        </button>
      </nav>
    </header>
  );
};

export default TopNav;
