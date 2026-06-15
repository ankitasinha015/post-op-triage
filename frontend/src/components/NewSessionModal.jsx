import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { api } from '../lib/api';

export default function NewSessionModal({ onClose, onCreated }) {
  const [scenarios, setScenarios] = useState([]);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.getScenarios().then(setScenarios).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!selected) return;
    setCreating(true);
    try {
      const session = await api.createSession({
        surgery_type: selected.surgery_type,
        recovery_day: selected.recovery_day,
        patient_name: selected.patient_name,
      });
      onCreated(session);
    } catch (e) {
      console.error('Failed to create session:', e);
    }
    setCreating(false);
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="text-lg font-semibold text-slate-900">New check-in</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-4 max-h-80 overflow-y-auto">
          <p className="text-sm text-slate-500 mb-3">Select a clinical scenario:</p>
          <div className="flex flex-col gap-2">
            {scenarios.map((s, i) => (
              <button
                key={i}
                onClick={() => setSelected(s)}
                className={`text-left px-4 py-3 rounded-xl border transition-colors ${
                  selected === s
                    ? 'border-teal-300 bg-teal-50'
                    : 'border-slate-100 hover:border-slate-200'
                }`}
              >
                <p className="font-medium text-sm text-slate-900">{s.name || s.patient_name}</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {s.surgery_type} · Day {s.recovery_day}
                </p>
                {s.description && (
                  <p className="text-xs text-slate-400 mt-1">{s.description}</p>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={!selected || creating}
            className="px-4 py-2 text-sm bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {creating ? 'Starting...' : 'Start check-in'}
          </button>
        </div>
      </div>
    </div>
  );
}
