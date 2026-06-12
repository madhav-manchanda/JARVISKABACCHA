import React, { useState, useEffect } from 'react';
import { Users, Search, Plus, Trash2, Edit, Phone, MessageSquare } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { motion } from 'framer-motion';

const Contacts = () => {
  const { token } = useAuth();
  const [contacts, setContacts] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const host = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

  const fetchContacts = async () => {
    try {
      const res = await axios.get(`${host}/contacts`, { headers: { Authorization: `Bearer ${token}` } });
      setContacts(res.data || []);
    } catch (err) {
      console.error("Failed to fetch contacts", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContacts();
  }, [token]);

  const deleteContact = async (id, name) => {
    if (!window.confirm(`Delete contact '${name}'?`)) return;
    try {
      await axios.delete(`${host}/contacts/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      fetchContacts();
    } catch (err) {
      console.error("Failed to delete contact", err);
    }
  };

  const filteredContacts = contacts.filter(c => 
    c.name.toLowerCase().includes(search.toLowerCase()) || 
    (c.phone && c.phone.includes(search)) ||
    (c.upi_id && c.upi_id.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="p-8 h-full flex flex-col">
      <div className="flex justify-between items-center mb-8">
        <h2 className="text-2xl font-bold text-jarvis-textMain flex items-center gap-3">
          <Users className="text-jarvis-cyan" />
          Contacts
        </h2>
        <button className="neon-button text-sm py-2 px-4">
          <Plus className="w-4 h-4" /> Add Contact
        </button>
      </div>

      <div className="glass-card p-2 mb-6 flex items-center gap-2">
        <Search className="w-5 h-5 text-jarvis-textMuted ml-2" />
        <input 
          type="text" 
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search contacts..." 
          className="flex-1 bg-transparent border-none text-jarvis-textMain focus:outline-none focus:ring-0 px-2 font-mono text-sm"
        />
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-jarvis-textMuted font-mono animate-pulse">Syncing address book...</div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 font-mono text-jarvis-textMuted text-xs uppercase tracking-wider sticky top-0 backdrop-blur-md">
              <tr>
                <th className="px-6 py-4">Name</th>
                <th className="px-6 py-4">Phone / WhatsApp</th>
                <th className="px-6 py-4">UPI ID</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredContacts.map(contact => (
                <motion.tr initial={{ opacity: 0 }} animate={{ opacity: 1 }} key={contact.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4 font-bold text-jarvis-cyan">{contact.name}</td>
                  <td className="px-6 py-4 text-jarvis-textMain font-mono">
                    <div className="flex items-center gap-2">
                      <Phone className="w-3 h-3 text-jarvis-textMuted" />
                      {contact.phone || 'N/A'}
                      {contact.whatsapp === 1 && <MessageSquare className="w-3 h-3 text-green-400 ml-2" title="WhatsApp enabled" />}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-jarvis-textMuted font-mono text-xs">{contact.upi_id || 'N/A'}</td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-jarvis-blue hover:bg-jarvis-blue/20 p-2 rounded-lg transition-colors mr-2">
                      <Edit className="w-4 h-4" />
                    </button>
                    <button 
                      onClick={() => deleteContact(contact.id, contact.name)}
                      className="text-jarvis-alert hover:bg-jarvis-alert/20 p-2 rounded-lg transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </motion.tr>
              ))}
              {filteredContacts.length === 0 && (
                <tr>
                  <td colSpan="4" className="px-6 py-8 text-center text-jarvis-textMuted font-mono">
                    No contacts found.
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

export default Contacts;
