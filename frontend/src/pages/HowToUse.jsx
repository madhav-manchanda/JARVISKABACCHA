import React from 'react';
import { Globe, Search, Play, BookOpen } from 'lucide-react';

const HowToUse = () => {
  const features = [
    {
      icon: <Globe className="text-blue-400 w-6 h-6" />,
      title: "Google Search",
      description: "Ask Jarvis to search the web for any information. It will summarize the top results for you.",
      examples: [
        "Search Google for the latest news on AI",
        "Who won the world cup in 2022?",
        "Google the weather in London right now"
      ]
    },
    {
      icon: <Search className="text-purple-400 w-6 h-6" />,
      title: "Google Dorking (Advanced Search)",
      description: "Jarvis can craft highly-specialized Google Dorks to find hidden files, direct downloads, or bypass retail sites. It strictly enforces file types.",
      examples: [
        "Find the PDF of 'Introduction to Machine Learning' book",
        "Use dorking to find open directories containing cyberpunk wallpapers",
        "Search for the epub file of 'The Martian' using google dork"
      ]
    },
    {
      icon: <Play className="text-red-400 w-6 h-6" />,
      title: "Media (YouTube & Spotify)",
      description: "Play music or videos. Jarvis will construct the correct URLs and launch the web player for you.",
      examples: [
        "Play Blinding Lights on Spotify",
        "Search YouTube for MrBeast latest video",
        "Open cyberpunk music on youtube"
      ]
    }
  ];

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-64px)] relative bg-jarvis-bg p-6 overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-jarvis-primary/5 blur-[100px] rounded-full pointer-events-none" />

      {/* Header Info */}
      <div className="flex items-center gap-3 mb-6 z-10 relative">
        <BookOpen className="text-jarvis-primary w-6 h-6" />
        <h2 className="text-2xl font-bold text-white font-montserrat">How to Use Jarvis</h2>
      </div>

      <div className="flex-1 overflow-y-auto space-y-8 pr-4 z-10 pb-24 custom-scrollbar">
        
        {/* Intro */}
        <section className="glass-card p-6 rounded-2xl border border-white/10">
          <p className="text-jarvis-textMain leading-relaxed mb-4">
            Welcome to the Jarvis Command Hub! You can communicate with Jarvis using the text input or by holding the Microphone button. 
            Jarvis acts as a centralized brain capable of performing complex web scraping, parsing requests, and pulling data directly into your dashboard.
          </p>
          <p className="text-sm text-jarvis-textMuted mt-2">
            Everything runs in the cloud. Jarvis will launch new browser tabs for media or display search results directly in the chat timeline.
          </p>
        </section>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {features.map((feature, idx) => (
            <div key={idx} className="glass-card p-5 rounded-2xl border border-white/5 hover:border-jarvis-cyan/30 transition-all hover:bg-white/5 group">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-[12px] bg-[#121212] border border-white/5 group-hover:scale-110 transition-transform shadow-[0_0_10px_rgba(168,85,247,0.1)]">
                  {feature.icon}
                </div>
                <h3 className="text-lg font-bold text-white font-montserrat">{feature.title}</h3>
              </div>
              <p className="text-sm text-jarvis-textMuted mb-4 leading-relaxed font-inter">
                {feature.description}
              </p>
              <div>
                <h4 className="text-[10px] font-mono text-jarvis-textMuted/50 mb-2 uppercase tracking-wider">Example Prompts</h4>
                <ul className="space-y-2">
                  {feature.examples.map((ex, i) => (
                    <li key={i} className="text-xs font-mono text-jarvis-primary/90 bg-jarvis-primary/10 border border-jarvis-primary/20 px-2 py-1.5 rounded-[8px] inline-block mr-2 mb-2">
                      "{ex}"
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
};

export default HowToUse;
