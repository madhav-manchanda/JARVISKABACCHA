import React, { useState, useRef, useEffect } from 'react';
import { Mic, Send, Play, Server, Smartphone, AlertTriangle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { useWebSocket } from '../hooks/useWebSocket';

const CommandHub = () => {
  const { token } = useAuth();
  const [inputText, setInputText] = useState('');
  const [messages, setMessages] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmationModal, setConfirmationModal] = useState(null); // { payload, message }
  
  // Create a consistent session ID for the WS
  const [sessionId] = useState(() => Math.random().toString(36).substring(2, 15));
  const { messages: wsMessages, status: wsStatus } = useWebSocket(sessionId);
  
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const host = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

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
      const res = await axios.post(`${host}/command/text`, 
        { text: userText, session_id: sessionId },
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

  const sendVoiceCommand = async (audioBlob) => {
    setLoading(true);
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('session_id', sessionId);

    try {
      const res = await axios.post(`${host}/command/voice`, formData, {
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

  const handleJarvisResponse = (data) => {
    if (!data.success) {
      addMessage('assistant', data.response_text || 'Action failed.', { target: 'server' });
      return;
    }

    addMessage('assistant', data.response_text, {
      audioUrl: data.response_audio_url ? `${host}${data.response_audio_url}` : null,
      target: data.execution_target,
      intent: data.intent
    });

    if (data.intent?.confirmation_required) {
      setConfirmationModal({
        message: data.intent.confirmation_message || "Are you sure you want to proceed?",
        payload: {
          session_id: sessionId,
          confirmed: false, // will be set on click
          dork_query: data.intent.action === 'google_dork' ? data.intent.params?.user_intent : undefined,
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
      const res = await axios.post(`${host}/command/confirm`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });
      addMessage('assistant', res.data.response_text, { target: res.data.execution_target });
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
      <div className="flex justify-between items-center mb-6 z-10">
        <h2 className="text-2xl font-bold text-jarvis-textMain">Command Hub</h2>
        <div className="flex items-center gap-2 text-sm font-mono">
          <span className={`w-2 h-2 rounded-full ${wsStatus === 'Connected' ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-jarvis-alert'}`}></span>
          <span className="text-jarvis-textMuted">WS: {wsStatus}</span>
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-4 z-10 pb-20 custom-scrollbar">
        <AnimatePresence>
          {messages.map((msg) => (
            <motion.div 
              key={msg.id}
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[70%] p-4 rounded-2xl ${
                msg.role === 'user' 
                  ? 'bg-jarvis-cyan/10 border border-jarvis-cyan/20 text-jarvis-cyan rounded-tr-none' 
                  : msg.role === 'system'
                    ? 'bg-jarvis-alert/10 border border-jarvis-alert/30 text-jarvis-alert'
                    : 'glass-card rounded-tl-none'
              }`}>
                {msg.role === 'assistant' && (
                  <div className="flex items-center gap-2 mb-2 text-xs font-mono text-jarvis-textMuted">
                    {msg.target === 'server' ? (
                      <span className="flex items-center gap-1 text-green-400"><Server className="w-3 h-3"/> Server</span>
                    ) : (
                      <span className="flex items-center gap-1 text-jarvis-blue"><Smartphone className="w-3 h-3"/> Device</span>
                    )}
                    {msg.intent?.action && <span> | {msg.intent.action}</span>}
                  </div>
                )}
                
                <p className="text-sm leading-relaxed">{msg.text}</p>
                
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
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
              <div className="glass-card p-4 rounded-2xl rounded-tl-none flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-jarvis-cyan animate-bounce" />
                <div className="w-2 h-2 rounded-full bg-jarvis-cyan animate-bounce" style={{ animationDelay: '0.2s'}} />
                <div className="w-2 h-2 rounded-full bg-jarvis-cyan animate-bounce" style={{ animationDelay: '0.4s'}} />
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

      {/* Input Area */}
      <div className="absolute bottom-6 left-6 right-6 z-20">
        <div className="glass-card p-2 flex items-center gap-2 rounded-xl">
          <button
            onMouseDown={startRecording}
            onMouseUp={stopRecording}
            onMouseLeave={stopRecording}
            onTouchStart={startRecording}
            onTouchEnd={stopRecording}
            className={`p-3 rounded-xl transition-all relative ${
              isRecording 
                ? 'bg-jarvis-alert/20 text-jarvis-alert border border-jarvis-alert/50' 
                : 'bg-white/5 text-jarvis-textMuted hover:text-jarvis-cyan hover:bg-white/10 border border-transparent'
            }`}
          >
            {isRecording && (
              <span className="absolute inset-0 rounded-xl border-2 border-jarvis-alert animate-ping" />
            )}
            <Mic className="w-5 h-5 relative z-10" />
          </button>

          <form onSubmit={handleSendText} className="flex-1 flex items-center gap-2">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Type a command or use voice..."
              className="flex-1 bg-transparent border-none text-jarvis-textMain focus:outline-none focus:ring-0 px-2 placeholder:text-jarvis-textMuted/50 font-mono text-sm"
              disabled={isRecording}
            />
            <button 
              type="submit"
              disabled={!inputText.trim() || loading}
              className="p-3 bg-jarvis-cyan/10 text-jarvis-cyan rounded-xl hover:bg-jarvis-cyan/20 transition-all border border-jarvis-cyan/30 disabled:opacity-50"
            >
              <Send className="w-5 h-5" />
            </button>
          </form>
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
