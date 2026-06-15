import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw, Plus, AlertTriangle, ArrowRight, Eye, Check, AlertCircle } from 'lucide-react';
import { api } from '../lib/api';
import { riskColor, statusBadge, initials, timeAgo } from '../lib/utils';
import NewSessionModal from '../components/NewSessionModal';

export default function Dashboard() {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNewSession, setShowNewSession] = useState(false);
  const navigate = useNavigate();

  const loadWorklist = async () => {
    setLoading(true);
    try {
      const data = await api.getWorklist();
      setPatients(data);
    } catch (e) {
      console.error('Failed to load worklist:', e);
    }
    setLoading(false);
  };

  useEffect(() => { loadWorklist(); }, []);

  const urgentPatients = patients.filter(p => p.risk_score >= 60);
  const monitorPatients = patients.filter(p => p.risk_score >= 30 && p.risk_score < 60);
  const stablePatients = patients.filter(p => p.risk_score < 30);

  const stats = [
    { label: 'Active', value: patients.length, color: '' },
    { label: 'Needs review', value: urgentPatients.length, color: 'text-red-600' },
    { label: 'Monitoring', value: monitorPatients.length, color: 'text-amber-600' },
    { label: 'On track', value: stablePatients.length, color: 'text-emerald-600' },
  ];

  const StatusIcon = ({ score }) => {
    if (score >= 60) return <AlertCircle className="w-3.5 h-3.5" />;
    if (score >= 30) return <Eye className="w-3.5 h-3.5" />;
    return <Check className="w-3.5 h-3.5" />;
  };

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Care board</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {patients.length} patient{patients.length !== 1 ? 's' : ''}
            {urgentPatients.length > 0 && ` · ${urgentPatients.length} need attention`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadWorklist}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors text-slate-600"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => setShowNewSession(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            New check-in
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl px-4 py-3 border border-slate-100">
            <p className="text-xs text-slate-500 uppercase tracking-wide">{s.label}</p>
            <p className={`text-2xl font-semibold mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Urgent alert banner */}
      {urgentPatients.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-5 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
          <span className="text-sm text-red-700 font-medium flex-1">
            {urgentPatients[0].patient_name} flagged urgent
            {urgentPatients[0].latest_alert && ` — ${urgentPatients[0].latest_alert}`}
          </span>
          <button
            onClick={() => navigate(`/patient/${urgentPatients[0].id}`)}
            className="text-xs font-medium px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            Review now
          </button>
        </div>
      )}

      {/* Patient cards */}
      <div className="flex flex-col gap-2">
        {patients.map(p => {
          const risk = riskColor(p.risk_score);
          const status = statusBadge(p.risk_score);

          return (
            <div
              key={p.id}
              onClick={() => navigate(`/patient/${p.id}`)}
              className="bg-white rounded-xl border border-slate-100 px-5 py-4 cursor-pointer hover:border-slate-200 hover:shadow-sm transition-all"
              style={{ borderLeft: `3px solid ${risk.border}` }}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium"
                    style={{ background: risk.bg, color: risk.text }}
                  >
                    {initials(p.patient_name)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-900">{p.patient_name}</span>
                      <span
                        className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${status.cls}`}
                      >
                        <StatusIcon score={p.risk_score} />
                        {status.label}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {p.surgery_type} · Day {p.recovery_day} · Last check-in {timeAgo(p.started_at)}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-semibold" style={{ color: risk.border }}>
                    {p.risk_score}
                  </div>
                  <div className="text-xs text-slate-400">risk score</div>
                </div>
              </div>

              {/* Signals */}
              {p.triggered_signals && p.triggered_signals.length > 0 && (
                <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                  {p.triggered_signals.slice(0, 4).map((sig, i) => (
                    <span
                      key={i}
                      className="text-xs px-2.5 py-0.5 rounded-full"
                      style={{ background: risk.bg, color: risk.text }}
                    >
                      {sig.replaceAll('_', ' ')}
                    </span>
                  ))}
                  {p.symptom_count > 0 && (
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                      {p.symptom_count} symptom{p.symptom_count !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              )}

              {/* Bottom row */}
              <div className="flex items-center justify-between mt-3">
                <div className="flex-1" />
                <button
                  className="flex items-center gap-1 text-xs font-medium text-teal-700 hover:text-teal-800"
                  onClick={(e) => { e.stopPropagation(); navigate(`/patient/${p.id}`); }}
                >
                  Open <ArrowRight className="w-3 h-3" />
                </button>
              </div>
            </div>
          );
        })}

        {!loading && patients.length === 0 && (
          <div className="text-center py-16 text-slate-400">
            <p className="text-lg mb-2">No patients yet</p>
            <p className="text-sm">Start a new check-in to begin</p>
          </div>
        )}
      </div>

      {showNewSession && (
        <NewSessionModal
          onClose={() => setShowNewSession(false)}
          onCreated={(session) => {
            setShowNewSession(false);
            navigate(`/chat/${session.id}`);
          }}
        />
      )}
    </div>
  );
}
