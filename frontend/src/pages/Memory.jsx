import React, { useState, useEffect } from 'react';
import { Database, Search, Plus, Trash2, Edit } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { motion } from 'framer-motion';

const Memory = () => {
  const { token } = useAuth();
  const [facts, setFacts] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const host = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

  const fetchFacts = async () => {
    try {
      const res = await axios.get(`${host}/memory/facts`, { headers: { Authorization: `Bearer ${token}` } });
      setFacts(res.data.facts || []);
    } catch (err) {
      console.error("Failed to fetch facts", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFacts();
  }, [token]);

  const deleteFact = async (key) => {
    if (!window.confirm(`Delete fact '${key}'?`)) return;
    try {
      await axios.delete(`${host}/memory/facts/${key}`, { headers: { Authorization: `Bearer ${token}` } });
      fetchFacts();
    } catch (err) {
      console.error("Failed to delete fact", err);
    }
  };

  const filteredFacts = facts.filter(f => 
    f.key.toLowerCase().includes(search.toLowerCase()) || 
    f.value.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 h-full flex flex-col">
      <div className="flex justify-between items-center mb-8">
        <h2 className="text-2xl font-bold text-jarvis-textMain flex items-center gap-3">
          <Database className="text-jarvis-cyan" />
          Memory Core
        </h2>
        <button className="neon-button text-sm py-2 px-4">
          <Plus className="w-4 h-4" /> Add Fact
        </button>
      </div>

      <div className="glass-card p-2 mb-6 flex items-center gap-2">
        <Search className="w-5 h-5 text-jarvis-textMuted ml-2" />
        <input 
          type="text" 
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search memories..." 
          className="flex-1 bg-transparent border-none text-jarvis-textMain focus:outline-none focus:ring-0 px-2 font-mono text-sm"
        />
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-jarvis-textMuted font-mono animate-pulse">Loading core memories...</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 font-mono text-jarvis-textMuted text-xs uppercase tracking-wider sticky top-0 backdrop-blur-md">
              <tr>
                <th className="px-6 py-4">Key</th>
                <th className="px-6 py-4">Value</th>
                <th className="px-6 py-4">Last Updated</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredFacts.map(fact => (
                <motion.tr initial={{ opacity: 0 }} animate={{ opacity: 1 }} key={fact.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4 font-bold text-jarvis-cyan">{fact.key}</td>
                  <td className="px-6 py-4 text-jarvis-textMain font-mono">{fact.value}</td>
                  <td className="px-6 py-4 text-jarvis-textMuted font-mono text-xs">{new Date(fact.updated_at).toLocaleString()}</td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-jarvis-blue hover:bg-jarvis-blue/20 p-2 rounded-lg transition-colors mr-2">
                      <Edit className="w-4 h-4" />
                    </button>
                    <button 
                      onClick={() => deleteFact(fact.key)}
                      className="text-jarvis-alert hover:bg-jarvis-alert/20 p-2 rounded-lg transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </motion.tr>
              ))}
              {filteredFacts.length === 0 && (
                <tr>
                  <td colSpan="4" className="px-6 py-8 text-center text-jarvis-textMuted font-mono">
                    No memories found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default Memory;
