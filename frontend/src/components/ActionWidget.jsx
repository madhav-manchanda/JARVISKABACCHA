import React from 'react';
import { ExternalLink, Search, Globe } from 'lucide-react';

const ActionWidget = ({ intent, followUps = [] }) => {
  // Combine main intent and any follow-up actions into one array to process
  const actionsToRender = [];
  
  if (intent && intent.action && intent.action !== 'general_chat' && intent.action !== 'clarify') {
    actionsToRender.push(intent);
  }
  
  if (Array.isArray(followUps)) {
    actionsToRender.push(...followUps);
  }

  if (actionsToRender.length === 0) return null;

  const renderActionCard = (actionData, idx) => {
    const { action, params } = actionData;

    switch (action) {
      case 'open_url':
        return (
          <a key={idx} href={params?.url} target="_blank" rel="noopener noreferrer" 
             className="flex items-center gap-3 p-3 mt-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-jarvis-cyan/30 transition-all group">
            <div className="w-8 h-8 rounded-full bg-jarvis-cyan/20 flex items-center justify-center text-jarvis-cyan group-hover:scale-110 transition-transform">
              <ExternalLink className="w-4 h-4" />
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="text-sm font-medium text-jarvis-textMain truncate">{params?.url}</p>
              <p className="text-xs text-jarvis-textMuted font-mono">Click to open link</p>
            </div>
          </a>
        );

      case 'google_search':
        return (
          <div key={idx} className="flex items-center gap-3 p-3 mt-2 rounded-xl bg-white/5 border border-white/10">
            <div className="w-8 h-8 rounded-full bg-[#4285F4]/20 flex items-center justify-center text-[#4285F4]">
              <Search className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-jarvis-textMain">Google Search</p>
              <p className="text-xs text-jarvis-textMuted font-mono truncate">Query: {params?.query}</p>
            </div>
          </div>
        );

      default:
        // Generic fallback for any other unhandled action
        return (
          <div key={idx} className="flex items-center gap-3 p-3 mt-2 rounded-xl bg-white/5 border border-white/10 opacity-70">
            <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-jarvis-textMuted">
              <Globe className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-jarvis-textMain capitalize">{action.replace('_', ' ')}</p>
              <p className="text-xs text-jarvis-textMuted font-mono">Action executed</p>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="flex flex-col gap-2 mt-2 w-full max-w-sm">
      {actionsToRender.map((action, idx) => renderActionCard(action, idx))}
    </div>
  );
};

export default ActionWidget;
