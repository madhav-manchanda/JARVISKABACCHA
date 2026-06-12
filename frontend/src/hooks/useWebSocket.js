import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

export const useWebSocket = (sessionId) => {
  const { token } = useAuth();
  const [ws, setWs] = useState(null);
  const [status, setStatus] = useState('Disconnected');
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    if (!token || !sessionId) return;

    // Use current host, assuming the FastAPI backend runs on the same host but port 8000
    // Adjust logic if needed based on environment
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
    
    const wsUrl = `${protocol}//${host}/ws/${sessionId}?token=${token}`;
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      setStatus('Connected');
    };

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setMessages(prev => [...prev, data]);
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };

    websocket.onclose = () => {
      setStatus('Disconnected');
    };

    websocket.onerror = (error) => {
      console.error("WebSocket Error:", error);
      setStatus('Error');
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [token, sessionId]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return { ws, status, messages, clearMessages };
};
