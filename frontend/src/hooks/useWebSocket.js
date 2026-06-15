import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

export const useWebSocket = (sessionId) => {
  const { token } = useAuth();
  const [ws, setWs] = useState(null);
  const [status, setStatus] = useState('Disconnected');
  const [messages, setMessages] = useState([]);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  const connect = useCallback(() => {
    if (!token || !sessionId) return;

    // Vite proxy forwards /ws to backend. Use same host as the page.
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${sessionId}?token=${token}`;
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      setStatus('Connected');
      // Clear any pending reconnects
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
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
      
      // Check if token expired by pinging health. The interceptor in main.jsx will handle 401s.
      axios.get('/health', { headers: { Authorization: `Bearer ${token}` } })
        .then(() => {
          // Token is fine, backend just dropped us or network blip. Reconnect in 3s.
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        })
        .catch(() => {
          // If it fails due to auth, main.jsx interceptor reloads the page.
          // If it fails due to server down, still try to reconnect.
          reconnectTimeoutRef.current = setTimeout(connect, 5000);
        });
    };

    websocket.onerror = (error) => {
      console.error("WebSocket Error:", error);
      setStatus('Error');
    };

    setWs(websocket);
    wsRef.current = websocket;
  }, [token, sessionId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return { ws, status, messages, clearMessages };
};
