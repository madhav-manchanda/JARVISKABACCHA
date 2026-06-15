import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Lock, User, Terminal } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [greeting, setGreeting] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const fullGreeting = "Securing Connection to Jarvis VPS Core...";

  useEffect(() => {
    let index = 0;
    const interval = setInterval(() => {
      setGreeting(fullGreeting.slice(0, index));
      index++;
      if (index > fullGreeting.length) clearInterval(interval);
    }, 50);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const response = await axios.post(`/auth/login`, {
        username,
        password
      });
      
      if (response.data && response.data.access_token) {
        login(response.data.access_token);
        navigate('/');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed. Please check credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-jarvis-bg">
      {/* Background glow effects */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-jarvis-cyan/10 blur-[120px] rounded-full pointer-events-none" />
      
      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="glass-card w-full max-w-md p-8 relative z-10"
      >
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 rounded-full bg-jarvis-bgSecondary border border-jarvis-cyan/30 flex items-center justify-center shadow-[0_0_15px_rgba(0,242,254,0.3)]">
            <Terminal className="text-jarvis-cyan w-8 h-8" />
          </div>
        </div>

        <div className="h-8 mb-6 flex justify-center items-center">
          <p className="text-jarvis-cyan font-mono text-sm tracking-wider">
            {greeting}
            <motion.span 
              animate={{ opacity: [1, 0] }} 
              transition={{ repeat: Infinity, duration: 0.8 }}
            >
              _
            </motion.span>
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded bg-jarvis-alert/10 border border-jarvis-alert/50 text-jarvis-alert text-sm font-mono text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <User className="text-jarvis-textMuted w-5 h-5" />
            </div>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="glass-input pl-10"
              placeholder="Username"
              required
            />
          </div>

          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Lock className="text-jarvis-textMuted w-5 h-5" />
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="glass-input pl-10"
              placeholder="Password"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="neon-button w-full"
          >
            {loading ? 'AUTHENTICATING...' : 'INITIALIZE'}
          </button>
        </form>
      </motion.div>
    </div>
  );
};

export default Login;
