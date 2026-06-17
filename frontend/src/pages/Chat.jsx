import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, Heart, Check, ArrowLeft, Loader2 } from 'lucide-react';
import { api } from '../lib/api';
import NewSessionModal from '../components/NewSessionModal';

export default function Chat() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [conclusion, setConclusion] = useState(null);
  const [showNewSession, setShowNewSession] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (sessionId) loadSession();
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSession = async () => {
    try {
      const [s, msgs] = await Promise.all([
        api.getSession(sessionId),
        api.getMessages(sessionId),
      ]);
      setSession(s);
      setMessages(msgs);

      const conc = await api.getConclusion(sessionId).catch(() => null);
      setConclusion(conc);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || sending || !sessionId) return;
    const msg = input.trim();
    setInput('');
    setSending(true);

    setMessages(prev => [...prev, { role: 'user', content: msg }]);

    try {
      const res = await api.sendMessage(sessionId, msg);

      if (res.is_conclusion && res.conclusion) {
        setConclusion(res.conclusion);
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: res.conclusion.summary || res.reply,
        }]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: res.reply }]);
      }

    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "I'm having trouble responding right now. Please try again.",
      }]);
    }

    setSending(false);
    inputRef.current?.focus();
  };

  const patientTurns = messages.filter(m => m.role === 'user').length;
  const totalTurns = 4;

  // Parse JSON conclusion from assistant messages so raw JSON never shows
  const parseMessageContent = (content) => {
    if (typeof content !== 'string') return content;
    const trimmed = content.trim();
    // Detect raw JSON or markdown-wrapped JSON
    let jsonStr = trimmed;
    if (trimmed.startsWith('```')) {
      jsonStr = trimmed.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
    }
    if (jsonStr.startsWith('{') && jsonStr.includes('"conclusion"')) {
      try {
        const parsed = JSON.parse(jsonStr);
        if (parsed.conclusion) {
          if (!conclusion) setConclusion(parsed);
          const parts = [];
          if (parsed.summary) parts.push(parsed.summary);
          if (parsed.guidance) parts.push(parsed.guidance);
          if (parsed.next_step) parts.push(`Next step: ${parsed.next_step}`);
          return parts.join('\n\n') || content;
        }
      } catch {}
    }
    return content;
  };

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Heart className="w-12 h-12 text-teal-300 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-700 mb-2">Start a check-in</h2>
          <p className="text-sm text-slate-500 mb-4">Select a scenario to begin a patient conversation</p>
          <button
            onClick={() => setShowNewSession(true)}
            className="px-4 py-2 text-sm bg-teal-600 text-white rounded-lg hover:bg-teal-700"
          >
            New check-in
          </button>
          {showNewSession && (
            <NewSessionModal
              onClose={() => setShowNewSession(false)}
              onCreated={(s) => { setShowNewSession(false); navigate(`/chat/${s.id}`); }}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Chat area */}
      <div className="flex-1 flex flex-col">
        {/* Chat header */}
        <div className="bg-teal-700 text-white px-5 py-4">
          <div className="flex items-center gap-3 mb-3">
            <button
              onClick={() => navigate('/chat')}
              className="p-1 rounded hover:bg-teal-600 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center">
              <Heart className="w-4 h-4" />
            </div>
            <div>
              <p className="font-medium text-sm">Recovery check-in</p>
              <p className="text-xs text-teal-200">
                {session ? `${session.patient_name} · ${session.surgery_type} · Day ${session.recovery_day}` : 'Loading...'}
              </p>
            </div>
          </div>
          {/* Progress bar */}
          <div className="flex gap-1.5">
            {Array.from({ length: totalTurns }).map((_, i) => (
              <div
                key={i}
                className="flex-1 h-1 rounded-full"
                style={{
                  background: i < patientTurns ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.25)',
                }}
              />
            ))}
          </div>
          <p className="text-xs text-teal-200 mt-1 text-right">
            {conclusion ? 'Check-in complete' : `Step ${Math.min(patientTurns + 1, totalTurns)} of ${totalTurns}`}
          </p>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 bg-slate-50 scrollbar-thin">
          <div className="max-w-xl mx-auto flex flex-col gap-3">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : ''}`}>
                {m.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full bg-teal-100 flex items-center justify-center shrink-0 mt-1">
                    <Heart className="w-3.5 h-3.5 text-teal-700" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] px-4 py-3 text-sm leading-relaxed whitespace-pre-line ${
                    m.role === 'user'
                      ? 'bg-teal-100 text-teal-900 rounded-2xl rounded-tr-sm'
                      : 'bg-white border border-slate-200 text-slate-700 rounded-2xl rounded-tl-sm'
                  }`}
                >
                  {m.role === 'assistant' ? parseMessageContent(m.content) : m.content}
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex gap-2">
                <div className="w-7 h-7 rounded-full bg-teal-100 flex items-center justify-center shrink-0">
                  <Heart className="w-3.5 h-3.5 text-teal-700" />
                </div>
                <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3">
                  <Loader2 className="w-4 h-4 text-teal-600 animate-spin" />
                </div>
              </div>
            )}

            {/* Conclusion card */}
            {conclusion && (
              <div className="bg-white border-2 border-teal-200 rounded-2xl p-5 mt-2">
                <div className="flex items-center gap-2 mb-3">
                  <Check className="w-5 h-5 text-teal-600" />
                  <span className="font-medium text-teal-800">Check-in complete</span>
                </div>
                {conclusion.session_summary && (
                  <p className="text-sm text-slate-600 mb-3">{conclusion.session_summary}</p>
                )}
                {conclusion.key_findings && conclusion.key_findings.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {conclusion.key_findings.map((f, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">{f}</span>
                    ))}
                  </div>
                )}
                <div className="flex gap-2 mt-3">
                  <button
                    onClick={() => { setShowNewSession(true); }}
                    className="text-xs px-3 py-1.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700"
                  >
                    Start new check-in
                  </button>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="bg-white border-t border-slate-200 px-5 py-3">
          {conclusion ? (
            <p className="text-sm text-slate-400 text-center py-2">
              This check-in is complete. Start a new session for another check-in.
            </p>
          ) : (
            <form
              onSubmit={(e) => { e.preventDefault(); handleSend(); }}
              className="flex gap-2 max-w-xl mx-auto"
            >
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Tell me how you're feeling..."
                disabled={sending}
                className="flex-1 px-4 py-2.5 rounded-full border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-teal-300 focus:border-teal-300 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || sending}
                className="w-10 h-10 rounded-full bg-teal-600 text-white flex items-center justify-center hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          )}
          <p className="text-[10px] text-slate-400 text-center mt-2">
            Educational demo · Not medical advice
          </p>
        </div>
      </div>

    </div>
  );
}
