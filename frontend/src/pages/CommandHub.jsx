import React, { useState, useRef, useEffect } from 'react';
import { Mic, Send, Paperclip, Skull, Play, Server, Smartphone, AlertTriangle, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../hooks/useWebSocket';
import ActionWidget from '../components/ActionWidget';

const CommandHub = () => {
  const { token } = useAuth();
  const [inputText, setInputText] = useState('');
  const [messages, setMessages] = useState(() => {
    const saved = localStorage.getItem('jarvis_messages');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (parsed.length > 0) return parsed;
    }
    // Default greeting if empty
    return [
      {
        id: 'initial-greeting',
        role: 'assistant',
        text: 'Hello! I am Jarvis, your personal AI assistant. How can I help you today?',
        target: 'server'
      }
    ];
  });
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deepSearch, setDeepSearch] = useState(false);
  const [confirmationModal, setConfirmationModal] = useState(null); // { payload, message }
  
  // Create a consistent session ID for the WS
  const [sessionId] = useState(() => {
    const saved = localStorage.getItem('jarvis_session');
    if (saved) return saved;
    const newSession = Math.random().toString(36).substring(2, 15);
    localStorage.setItem('jarvis_session', newSession);
    return newSession;
  });
  const { messages: wsMessages, status: wsStatus } = useWebSocket(sessionId);

  // Persist messages whenever they change
  useEffect(() => {
    localStorage.setItem('jarvis_messages', JSON.stringify(messages));
  }, [messages]);
  
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // All requests are relative — Vite proxy routes them to the backend

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, wsMessages]);

  const addMessage = (role, text, extras = {}) => {
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), role, text, ...extras }]);
  };

  const handleSendText = async (e) => {
    e?.preventDefault();
    if (!inputText.trim()) return;

    const userText = inputText;
    setInputText('');
    addMessage('user', userText);
    setLoading(true);

    try {
      const res = await axios.post(`/command/text`, 
        { text: userText, session_id: sessionId, deep_search: deepSearch },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      handleJarvisResponse(res.data);
    } catch (err) {
      addMessage('system', 'Error connecting to brain: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await sendVoiceCommand(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Mic access denied:', err);
      addMessage('system', 'Microphone access denied.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const sendVoiceCommand = async (blob) => {
    setLoading(true);
      const formData = new FormData();
      formData.append('audio', blob, 'recording.webm');
      formData.append('session_id', sessionId);
      formData.append('is_file_upload', 'false');

      try {
      const res = await axios.post(`/command/voice`, formData, {
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      if (res.data.transcribed_text) {
        addMessage('user', res.data.transcribed_text, { isVoice: true });
      }
      handleJarvisResponse(res.data);
    } catch (err) {
      addMessage('system', 'Voice processing failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    addMessage('user', `🎵 Uploaded audio file: ${file.name}`);
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('audio', file);
      formData.append('session_id', sessionId);
      formData.append('is_file_upload', 'true');

      const res = await axios.post(`/command/voice`, formData, {
        headers: { 
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${token}` 
        }
      });
      handleJarvisResponse(res.data);
    } catch (err) {
      addMessage('system', 'Error uploading file: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
      // Reset input
      e.target.value = '';
    }
  };

  const handleJarvisResponse = (data) => {
    if (!data.success) {
      addMessage('assistant', data.response_text || 'Action failed.', { target: 'server' });
      return;
    }

    addMessage('assistant', data.response_text, {
      audioUrl: data.response_audio_url ? `${data.response_audio_url}` : null,
      target: data.execution_target,
      intent: data.intent,
      followUps: data.follow_up_actions || [],
      payloadData: data.data
    });

    if (data.intent?.confirmation_required) {
      setConfirmationModal({
        message: data.intent.confirmation_message || "Are you sure you want to proceed?",
        payload: {
          session_id: sessionId,
          confirmed: false, // will be set on click
          dork_query: data.intent.action === 'google_dork' ? data.intent.params?.dork_query : undefined,
        }
      });
    }
  };

  const playAudio = (url) => {
    if (url) {
      const audio = new Audio(url);
      audio.play();
    }
  };

  const submitConfirmation = async (confirmed) => {
    const payload = { ...confirmationModal.payload, confirmed };
    setConfirmationModal(null);
    setLoading(true);

    try {
      const res = await axios.post(`/command/confirm`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });
      addMessage('assistant', res.data.response_text, { 
        target: res.data.execution_target,
        payloadData: res.data.data
      });
    } catch (err) {
      addMessage('system', 'Confirmation failed: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen relative bg-jarvis-bg p-6 overflow-hidden">
      
      {/* Background Glow */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-jarvis-blue/5 blur-[100px] rounded-full pointer-events-none" />

      {/* Header Info */}
      <div className="flex justify-between items-center mb-6 z-10 relative">
        <h2 className="text-2xl font-bold text-jarvis-textMain">Command Hub</h2>
        <div className="flex items-center gap-2 text-sm font-mono">
          <span className={`w-2 h-2 rounded-full ${wsStatus === 'Connected' ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-jarvis-alert'}`}></span>
          <span className="text-jarvis-textMuted">WS: {wsStatus}</span>
        </div>
      </div>

      {/* Global Processing Indicator */}
      <AnimatePresence>
        {loading && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }} 
            animate={{ height: 4, opacity: 1 }} 
            exit={{ height: 0, opacity: 0 }}
            className="absolute top-0 left-0 right-0 z-50 bg-gradient-to-r from-transparent via-jarvis-cyan to-transparent"
          >
            <motion.div 
              className="h-full bg-white/50 w-1/3 blur-sm"
              animate={{ x: ['-100%', '300%'] }}
              transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-4 z-10 pb-36 no-scrollbar custom-scrollbar">
        <div className="max-w-[1200px] mx-auto space-y-6 flex flex-col">
          <AnimatePresence>
            {messages.map((msg) => (
              <motion.div 
                key={msg.id}
                initial={{ opacity: 0, y: 10, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                className={`flex flex-col w-full ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="flex items-center gap-2 mb-2 ml-1">
                    <span className="w-2 h-2 rounded-full bg-jarvis-primary"></span>
                    <span className="font-montserrat text-sm text-jarvis-primary uppercase tracking-tighter font-bold">JARVIS</span>
                    {msg.intent?.action && <span className="text-xs font-mono text-jarvis-textMuted ml-2">[{msg.intent.action}]</span>}
                  </div>
                )}
                <div className={`p-4 md:p-6 transition-all duration-300 ${
                  msg.role === 'user' 
                    ? 'glass-card rounded-2xl rounded-tr-none max-w-[85%] md:w-fit hover:shadow-[0_0_15px_rgba(168,85,247,0.1)] border-jarvis-primary/20' 
                    : msg.role === 'system'
                      ? 'bg-jarvis-alert/10 border border-jarvis-alert/30 text-jarvis-alert rounded-2xl'
                      : 'glass-card rounded-2xl rounded-tl-none max-w-[90%] md:max-w-2xl'
                }`}>
                  
                  <p className="font-inter text-[16px] leading-[1.6] tracking-[0.01em] text-white">
                    {msg.text}
                  </p>
                
                {msg.role === 'assistant' && (msg.intent || msg.followUps?.length > 0) && (
                  <ActionWidget intent={msg.intent} followUps={msg.followUps} />
                )}

                {msg.payloadData?.results?.length > 0 && (
                  <div className="mt-4 space-y-3">
                    {msg.payloadData.results.map((r, i) => (
                      <a key={i} href={r.url} target="_blank" rel="noopener noreferrer" className="block p-3 bg-black/20 hover:bg-black/40 rounded-xl transition-all border border-jarvis-cyan/10 hover:border-jarvis-cyan/30 shadow-sm hover:shadow-[0_0_10px_rgba(0,242,254,0.1)] group">
                        <h4 className="text-sm font-semibold text-jarvis-cyan mb-1 group-hover:underline">{r.title}</h4>
                        <p className="text-xs text-jarvis-textMuted line-clamp-2">{r.snippet}</p>
                        <div className="flex items-center gap-1 text-[10px] text-jarvis-textMuted/50 mt-2 truncate">
                          <Search className="w-3 h-3" />
                          <span className="truncate">{r.url}</span>
                        </div>
                      </a>
                    ))}
                  </div>
                )}

                {msg.payloadData?.image_url && (
                  <div className="mt-4 overflow-hidden rounded-xl border border-jarvis-primary/30 shadow-[0_0_20px_rgba(168,85,247,0.15)] bg-black/50">
                    <img 
                      src={msg.payloadData.image_url} 
                      alt="AI Generated" 
                      className="w-full h-auto object-cover max-h-[500px]"
                      onError={(e) => {
                        if (!e.target.dataset.retried) {
                          e.target.dataset.retried = "true";
                          const prompt = msg.intent?.params?.prompt || "image";
                          e.target.src = `https://loremflickr.com/1024/1024/${encodeURIComponent(prompt)}`;
                        }
                      }}
                    />
                  </div>
                )}

                {msg.audioUrl && (
                  <button 
                    onClick={() => playAudio(msg.audioUrl)}
                    className="mt-3 flex items-center gap-2 text-xs bg-white/5 hover:bg-white/10 px-3 py-1.5 rounded-lg transition-colors text-jarvis-textMain"
                  >
                    <Play className="w-3 h-3 text-jarvis-cyan" /> Play Response
                  </button>
                )}
              </div>
            </motion.div>
          ))}
          {loading && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-start w-full opacity-60">
              <div className="glass-card px-4 py-3 rounded-full flex items-center gap-3">
                <div className="flex gap-1.5">
                  <div className="w-1.5 h-1.5 bg-jarvis-primary rounded-full animate-bounce" style={{ animationDelay: '0s'}} />
                  <div className="w-1.5 h-1.5 bg-jarvis-primary rounded-full animate-bounce" style={{ animationDelay: '0.2s'}} />
                  <div className="w-1.5 h-1.5 bg-jarvis-primary rounded-full animate-bounce" style={{ animationDelay: '0.4s'}} />
                </div>
                <span className="text-xs font-inter tracking-wider text-jarvis-textMuted uppercase">Processing...</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        
        {/* Live WS Events Inline */}
        {wsMessages.length > 0 && (
          <div className="mt-8 border-t border-white/10 pt-4">
            <h4 className="text-xs font-mono text-jarvis-textMuted mb-2">LIVE BACKGROUND TASKS</h4>
            {wsMessages.map((ws, idx) => (
              <div key={idx} className="text-xs font-mono text-jarvis-textMuted bg-black/40 p-2 rounded mb-1 border border-white/5">
                &gt; {JSON.stringify(ws)}
              </div>
            ))}
          </div>
        )}
        <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="absolute bottom-0 left-0 right-0 z-40 px-6 pb-6 pt-8 bg-gradient-to-t from-black via-black/80 to-transparent">
        <div className="max-w-[1200px] mx-auto space-y-4">
          
          {/* Deep Search Toggle Area */}
          <div className="flex justify-center mb-2">
            <button
              onClick={() => setDeepSearch(!deepSearch)}
              className={`glass-card px-6 py-2.5 rounded-full flex items-center gap-4 transition-all duration-300 group ${
                deepSearch ? 'border-jarvis-primary/50 shadow-[0_0_20px_rgba(168,85,247,0.2)] bg-[#121212]/80' : 'hover:border-jarvis-primary/30 hover:bg-[#121212]/70'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Skull className={`w-[18px] h-[18px] transition-colors ${deepSearch ? 'text-jarvis-primary drop-shadow-[0_0_8px_rgba(168,85,247,0.8)]' : 'text-jarvis-textMuted group-hover:text-white'}`} />
                <span className={`text-[13px] font-inter font-medium tracking-[0.15em] uppercase transition-colors ${deepSearch ? 'text-white drop-shadow-[0_0_5px_rgba(255,255,255,0.3)]' : 'text-jarvis-textMuted group-hover:text-white'}`}>Deep Search</span>
              </div>
              <div className={`w-11 h-6 rounded-full p-[2px] flex items-center transition-all duration-300 ${deepSearch ? 'bg-jarvis-primary shadow-[0_0_10px_rgba(168,85,247,0.5)]' : 'bg-[#1a1a24] border border-white/10 group-hover:border-white/20'}`}>
                <div className={`w-5 h-5 bg-white rounded-full shadow-sm transition-transform duration-300 ${deepSearch ? 'translate-x-5' : 'translate-x-0'}`} />
              </div>
            </button>
          </div>

          {/* Floating Input Dock */}
          <div className="glass-input p-2 rounded-3xl md:rounded-full flex items-center gap-2 shadow-2xl transition-all focus-within:border-jarvis-primary/40 focus-within:shadow-[0_0_30px_rgba(168,85,247,0.15)]">
            
            {/* Attach Button */}
            <label className={`w-12 h-12 flex items-center justify-center text-jarvis-textMuted hover:text-jarvis-primary transition-colors hover:bg-white/5 rounded-full cursor-pointer ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}>
              <Paperclip className="w-5 h-5" />
              <input type="file" accept="audio/*" onChange={handleFileUpload} disabled={loading} className="hidden" />
            </label>

            {/* Input Field */}
            <form onSubmit={handleSendText} className="flex-1 flex">
              <input 
                type="text" 
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={loading ? "Jarvis is processing..." : "Message Jarvis..."}
                disabled={loading}
                className="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none text-white placeholder:text-jarvis-textMuted/50 px-2 h-12 font-inter text-base"
              />
            </form>

            {/* Voice Button */}
            <button
              onMouseDown={loading ? undefined : startRecording}
              onMouseUp={loading ? undefined : stopRecording}
              onMouseLeave={loading ? undefined : stopRecording}
              onTouchStart={loading ? undefined : startRecording}
              onTouchEnd={loading ? undefined : stopRecording}
              disabled={loading}
              className={`w-12 h-12 flex items-center justify-center rounded-full transition-all relative ${
                isRecording 
                  ? 'text-jarvis-alert bg-jarvis-alert/10 shadow-[0_0_20px_rgba(245,158,11,0.3)]' 
                  : 'text-jarvis-textMuted hover:text-jarvis-primary hover:bg-white/5'
              }`}
            >
              {isRecording && <span className="absolute inset-0 rounded-full border border-jarvis-alert animate-ping" />}
              <Mic className="w-5 h-5 relative z-10" />
            </button>

            {/* Send Button */}
            <button 
              onClick={handleSendText}
              disabled={!inputText.trim() || loading}
              className={`w-12 h-12 flex items-center justify-center rounded-full transition-all ${
                inputText.trim() && !loading
                  ? 'bg-jarvis-primary text-white hover:opacity-90 shadow-[0_0_20px_rgba(168,85,247,0.4)] active:scale-95' 
                  : 'bg-white/5 text-jarvis-textMuted cursor-not-allowed'
              }`}
            >  
              <Send className="w-5 h-5 ml-0.5" />
            </button>
          </div>

        </div>
      </div>

      {/* Confirmation Modal */}
      <AnimatePresence>
        {confirmationModal && (
          <motion.div 
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}
              className="glass-card w-full max-w-sm p-6 border-jarvis-alert/30 shadow-[0_0_30px_rgba(245,158,11,0.15)]"
            >
              <div className="flex justify-center mb-4">
                <div className="w-12 h-12 rounded-full bg-jarvis-alert/10 flex items-center justify-center border border-jarvis-alert/30 text-jarvis-alert">
                  <AlertTriangle className="w-6 h-6" />
                </div>
              </div>
              <h3 className="text-lg font-bold text-center mb-2 text-white">Action Confirmation</h3>
              <p className="text-sm text-jarvis-textMuted text-center mb-6">{confirmationModal.message}</p>
              
              <div className="flex gap-3">
                <button onClick={() => submitConfirmation(false)} className="flex-1 px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5 transition-colors text-sm font-medium">
                  Cancel
                </button>
                <button onClick={() => submitConfirmation(true)} className="flex-1 px-4 py-2 rounded-lg bg-jarvis-alert/20 border border-jarvis-alert/50 text-jarvis-alert hover:bg-jarvis-alert/30 transition-colors text-sm font-bold tracking-wide">
                  Confirm Execute
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
};

export default CommandHub;
