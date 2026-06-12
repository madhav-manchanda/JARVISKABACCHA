import React, { useState, useEffect } from 'react';
import { Activity, HardDrive, Cpu, Clock, Trash2, Zap } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { motion } from 'framer-motion';

const Health = () => {
  const { token } = useAuth();
  const [healthData, setHealthData] = useState(null);
  const [timers, setTimers] = useState([]);
  const [loading, setLoading] = useState(true);

  const host = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

  const fetchData = async () => {
    try {
      const [healthRes, timersRes] = await Promise.all([
        axios.get(`${host}/health`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${host}/timers`, { headers: { Authorization: `Bearer ${token}` } })
      ]);
      setHealthData(healthRes.data);
      setTimers(timersRes.data);
    } catch (err) {
      console.error("Failed to fetch system data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, [token]);

  const cancelTimer = async (timerId) => {
    try {
      await axios.delete(`${host}/timers/${timerId}`, { headers: { Authorization: `Bearer ${token}` } });
      fetchData();
    } catch (err) {
      console.error("Failed to cancel timer", err);
    }
  };

  const MetricRing = ({ icon: Icon, label, value, unit, color }) => {
    const percentage = value ? Math.min(100, Math.max(0, value)) : 0;
    const strokeDasharray = `${percentage} 100`;

    return (
      <div className="glass-card p-6 flex flex-col items-center justify-center relative group">
        <Icon className={`w-6 h-6 mb-4 ${color}`} />
        <svg viewBox="0 0 36 36" className="w-24 h-24 stroke-current text-white/5 mb-2">
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            strokeWidth="3"
          />
          <path
            className={`${color} transition-all duration-1000 ease-out`}
            strokeDasharray={strokeDasharray}
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            strokeWidth="3"
          />
        </svg>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pt-2 text-center">
          <span className="text-xl font-bold text-jarvis-textMain">{value?.toFixed(1) || 0}</span>
          <span className="text-xs text-jarvis-textMuted ml-1">{unit}</span>
        </div>
        <span className="text-sm font-mono text-jarvis-textMuted uppercase tracking-wider">{label}</span>
      </div>
    );
  };

  if (loading && !healthData) {
    return <div className="p-8 text-jarvis-cyan font-mono animate-pulse">Initializing System Metrics...</div>;
  }

  return (
    <div className="p-8 h-full overflow-y-auto custom-scrollbar">
      <h2 className="text-2xl font-bold text-jarvis-textMain mb-8 flex items-center gap-3">
        <Activity className="text-jarvis-cyan" />
        System Diagnostics
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        <MetricRing 
          icon={Cpu} 
          label="CPU Load" 
          value={healthData?.cpu_percent} 
          unit="%" 
          color="text-jarvis-blue" 
        />
        <MetricRing 
          icon={Activity} 
          label="Memory Usage" 
          value={healthData?.memory_percent} 
          unit="%" 
          color="text-jarvis-cyan" 
        />
        <MetricRing 
          icon={HardDrive} 
          label="Disk Free" 
          value={healthData?.disk_free_gb ? (100 - (healthData.disk_free_gb / (healthData.disk_total_gb || 1) * 100)) : 0} 
          unit="%" 
          color="text-jarvis-alert" 
        />
        <div className="glass-card p-6 flex flex-col items-center justify-center">
          <Zap className="w-8 h-8 text-yellow-400 mb-4 animate-pulse" />
          <div className="text-2xl font-bold text-jarvis-textMain mb-1">
            {healthData?.uptime_hours?.toFixed(1) || 0} <span className="text-sm text-jarvis-textMuted font-normal">hrs</span>
          </div>
          <span className="text-sm font-mono text-jarvis-textMuted uppercase tracking-wider">Uptime</span>
        </div>
      </div>

      <h3 className="text-xl font-bold text-jarvis-textMain mb-6 flex items-center gap-3">
        <Clock className="text-jarvis-cyan" />
        Active Timers & Alarms
      </h3>

      <div className="glass-card overflow-hidden">
        {timers.length === 0 ? (
          <div className="p-8 text-center text-jarvis-textMuted font-mono">No active timers or alarms.</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 font-mono text-jarvis-textMuted text-xs uppercase tracking-wider">
              <tr>
                <th className="px-6 py-4">Label</th>
                <th className="px-6 py-4">Type</th>
                <th className="px-6 py-4">Status / Target</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {timers.map(t => (
                <motion.tr initial={{ opacity: 0 }} animate={{ opacity: 1 }} key={t.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4 font-medium text-jarvis-textMain">{t.label}</td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-1 bg-white/10 rounded-md text-xs font-mono">{t.type}</span>
                  </td>
                  <td className="px-6 py-4 text-jarvis-textMuted">{t.target_time || t.duration}</td>
                  <td className="px-6 py-4 text-right">
                    <button 
                      onClick={() => cancelTimer(t.id)}
                      className="text-jarvis-alert hover:bg-jarvis-alert/20 p-2 rounded-lg transition-colors"
                      title="Cancel Timer"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default Health;
