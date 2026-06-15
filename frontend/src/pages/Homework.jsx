import React, { useState } from 'react';
import { Upload, PenTool, Image as ImageIcon, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const Homework = () => {
  const { token } = useAuth();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [resultImage, setResultImage] = useState(null);
  const [detectedStyle, setDetectedStyle] = useState('');

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    if (selected) {
      setFile(selected);
      setPreview(URL.createObjectURL(selected));
    }
  };

  const handleGenerate = async () => {
    if (!file || !text.trim()) return;

    setLoading(true);
    setResultImage(null);
    setDetectedStyle('');

    try {
      const formData = new FormData();
      formData.append('reference_image', file);
      formData.append('text', text);

      const res = await axios.post('/homework/generate', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          Authorization: `Bearer ${token}`
        }
      });

      if (res.data.success) {
        setResultImage(res.data.image_url);
        setDetectedStyle(res.data.style);
      }
    } catch (err) {
      console.error(err);
      alert('Failed to generate homework: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-64px)] relative bg-jarvis-bg p-6 overflow-hidden pt-24">
      {/* Background Glow */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-jarvis-primary/5 blur-[100px] rounded-full pointer-events-none" />

      <div className="max-w-[1000px] mx-auto w-full flex-1 overflow-y-auto no-scrollbar pb-24">
        <div className="mb-8 text-center">
          <h2 className="text-3xl font-montserrat font-bold text-white mb-2 tracking-tight">AI Homework Writer</h2>
          <p className="text-jarvis-textMuted font-inter">Upload a sample of handwriting, and Jarvis will write your homework.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          
          {/* Left Column: Input */}
          <div className="space-y-6">
            <div className="glass-card p-6 rounded-3xl border border-white/5 bg-[#121212]/80 shadow-2xl">
              <h3 className="text-sm font-inter text-jarvis-textMuted uppercase tracking-widest mb-4 flex items-center gap-2">
                <ImageIcon className="w-4 h-4 text-jarvis-primary" /> Reference Photo
              </h3>
              
              <label className="border-2 border-dashed border-white/10 hover:border-jarvis-primary/50 transition-colors rounded-2xl p-8 flex flex-col items-center justify-center cursor-pointer bg-black/20 group h-48 relative overflow-hidden">
                <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" />
                {preview ? (
                  <img src={preview} alt="Preview" className="absolute inset-0 w-full h-full object-cover opacity-60 group-hover:opacity-40 transition-opacity" />
                ) : (
                  <Upload className="w-8 h-8 text-jarvis-textMuted mb-3 group-hover:text-jarvis-primary transition-colors" />
                )}
                <span className="text-sm font-inter font-medium text-white relative z-10 drop-shadow-md">
                  {file ? file.name : 'Click to upload handwriting sample'}
                </span>
              </label>
            </div>

            <div className="glass-card p-6 rounded-3xl border border-white/5 bg-[#121212]/80 shadow-2xl">
              <h3 className="text-sm font-inter text-jarvis-textMuted uppercase tracking-widest mb-4 flex items-center gap-2">
                <PenTool className="w-4 h-4 text-jarvis-primary" /> Homework Content
              </h3>
              <textarea 
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste your essay or answers here..."
                className="w-full h-48 bg-black/20 border border-white/10 rounded-2xl p-4 text-white font-inter focus:outline-none focus:border-jarvis-primary/50 transition-colors resize-none custom-scrollbar"
              />
            </div>

            <button 
              onClick={handleGenerate}
              disabled={loading || !file || !text.trim()}
              className="w-full py-4 rounded-full bg-jarvis-primary hover:bg-jarvis-primary/90 text-white font-montserrat font-bold tracking-wide flex items-center justify-center gap-3 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_20px_rgba(168,85,247,0.3)] active:scale-[0.98]"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" /> Generating Magic...
                </>
              ) : (
                'Write My Homework'
              )}
            </button>
          </div>

          {/* Right Column: Output */}
          <div className="glass-card p-6 rounded-3xl border border-white/5 bg-[#121212]/80 shadow-2xl flex flex-col">
            <h3 className="text-sm font-inter text-jarvis-textMuted uppercase tracking-widest mb-4 flex items-center justify-between">
              <span>Output Result</span>
              {detectedStyle && (
                <span className="text-xs bg-jarvis-primary/20 text-jarvis-primary px-3 py-1 rounded-full capitalize">
                  Style: {detectedStyle}
                </span>
              )}
            </h3>
            
            <div className="flex-1 bg-black/40 rounded-2xl border border-white/5 flex items-center justify-center overflow-hidden relative">
              {resultImage ? (
                <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="w-full h-full p-4 overflow-y-auto custom-scrollbar">
                  <img src={resultImage} alt="Generated Homework" className="w-full h-auto rounded shadow-2xl" />
                </motion.div>
              ) : (
                <div className="text-center p-6">
                  <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
                    <PenTool className="w-6 h-6 text-jarvis-textMuted/50" />
                  </div>
                  <p className="text-jarvis-textMuted font-inter text-sm">Your generated homework will appear here.</p>
                </div>
              )}
            </div>

            {resultImage && (
              <a 
                href={resultImage} 
                download="homework_assignment.jpg"
                className="mt-4 w-full py-3 rounded-full border border-jarvis-primary/50 text-jarvis-primary hover:bg-jarvis-primary/10 text-center font-inter font-medium transition-colors"
              >
                Download Image
              </a>
            )}
          </div>

        </div>
      </div>
    </div>
  );
};

export default Homework;
