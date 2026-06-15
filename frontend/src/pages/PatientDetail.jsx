import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft, MessageCircle, Stethoscope, Activity,
  Pill, AlertTriangle, Check, TrendingUp, TrendingDown,
} from 'lucide-react';
import { api } from '../lib/api';
import { riskColor, initials } from '../lib/utils';

export default function PatientDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [symptoms, setSymptoms] = useState([]);
  const [vitals, setVitals] = useState([]);
  const [meds, setMeds] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [riskScores, setRiskScores] = useState([]);
  const [conclusion, setConclusion] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [sessionId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [s, sym, v, m, a, r, c] = await Promise.all([
        api.getSession(sessionId),
        api.getSymptoms(sessionId),
        api.getVitals(sessionId),
        api.getMeds(sessionId),
        api.getAlerts(sessionId),
        api.getRiskScores(sessionId),
        api.getConclusion(sessionId).catch(() => null),
      ]);
      setSession(s);
      setSymptoms(sym);
      setVitals(v);
      setMeds(m);
      setAlerts(a);
      setRiskScores(r);
      setConclusion(c);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  if (loading || !session) {
    return <div className="p-6 text-slate-400">Loading...</div>;
  }

  const latestScore = riskScores.length > 0 ? riskScores[riskScores.length - 1].score : 0;
  const risk = riskColor(latestScore);
  const isConcluded = conclusion !== null;

  // Deduplicate symptoms
  const uniqueSymptoms = Object.values(
    symptoms.reduce((acc, s) => { acc[s.name] = s; return acc; }, {})
  );

  const recoveryDays = [1, 2, 3, 5, 7];
  const currentDayIdx = recoveryDays.findIndex(d => d >= session.recovery_day);

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-500"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center text-sm font-medium"
            style={{ background: risk.bg, color: risk.text }}
          >
            {initials(session.patient_name)}
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-semibold text-slate-900">{session.patient_name}</h1>
              <span
                className="text-xs font-medium px-2.5 py-0.5 rounded-full"
                style={{ background: isConcluded ? '#dcfce7' : '#dbeafe', color: isConcluded ? '#166534' : '#1e40af' }}
              >
                {isConcluded ? 'Concluded' : 'Live'}
              </span>
            </div>
            <p className="text-sm text-slate-500">
              {session.surgery_type} · Day {session.recovery_day} post-op
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Link
            to={`/chat/${sessionId}`}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
          >
            <MessageCircle className="w-3.5 h-3.5" /> View chat
          </Link>
          {latestScore >= 60 && (
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700">
              Contact care team
            </button>
          )}
        </div>
      </div>

      {/* Risk score + stats row */}
      <div className="grid grid-cols-[140px_1fr] gap-4 mb-6">
        <div className="bg-white rounded-xl border border-slate-100 p-4 text-center">
          <div
            className="w-20 h-20 rounded-full mx-auto mb-2 flex items-center justify-center"
            style={{ border: `3px solid ${risk.border}` }}
          >
            <span className="text-3xl font-semibold" style={{ color: risk.border }}>
              {latestScore}
            </span>
          </div>
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: risk.text }}>
            {risk.label} risk
          </p>
        </div>

        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Symptoms', value: uniqueSymptoms.length },
            { label: 'Vitals', value: vitals.length },
            { label: 'Meds', value: meds.length },
            { label: 'Alerts', value: alerts.length, danger: alerts.length > 0 },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-xl border border-slate-100 p-3 text-center">
              <p className="text-xs text-slate-500">{s.label}</p>
              <p className={`text-xl font-semibold mt-1 ${s.danger ? 'text-red-600' : ''}`}>{s.value}</p>
            </div>
          ))}

          {/* Recovery timeline */}
          <div className="col-span-4 bg-white rounded-xl border border-slate-100 px-4 py-3">
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-3">Recovery timeline</p>
            <div className="flex items-center">
              {recoveryDays.map((day, i) => {
                const isPast = day < session.recovery_day;
                const isCurrent = day === session.recovery_day;
                const isFuture = day > session.recovery_day;
                return (
                  <div key={day} className="flex items-center flex-1">
                    <div className="flex flex-col items-center flex-1">
                      <div
                        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                          isPast
                            ? 'bg-emerald-500 text-white'
                            : isCurrent
                            ? 'border-2 text-xs font-semibold'
                            : 'border border-dashed border-slate-300 text-slate-400'
                        }`}
                        style={isCurrent ? { borderColor: risk.border, color: risk.text, background: risk.bg } : {}}
                      >
                        {isPast ? <Check className="w-3 h-3" /> : day}
                      </div>
                      <span className={`text-[10px] mt-1 ${isCurrent ? 'font-medium text-slate-900' : 'text-slate-400'}`}>
                        {isCurrent ? 'Today' : `Day ${day}`}
                      </span>
                    </div>
                    {i < recoveryDays.length - 1 && (
                      <div
                        className="h-0.5 flex-1 -mx-1"
                        style={{ background: isPast ? '#10b981' : isCurrent ? risk.border : '#e2e8f0' }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Alert banner */}
      {alerts.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-700">
                {alerts[alerts.length - 1].severity.toUpperCase()}: {alerts[alerts.length - 1].summary}
              </p>
              {alerts[alerts.length - 1].recommended_action && (
                <p className="text-xs text-red-600 mt-1">{alerts[alerts.length - 1].recommended_action}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Two column layout */}
      <div className="grid grid-cols-2 gap-4">
        {/* Symptoms */}
        <div className="bg-white rounded-xl border border-slate-100 p-5">
          <h3 className="flex items-center gap-2 text-sm font-medium text-slate-700 mb-4">
            <Stethoscope className="w-4 h-4 text-slate-400" /> Symptoms
          </h3>
          {uniqueSymptoms.length > 0 ? (
            <div className="flex flex-col gap-3">
              {uniqueSymptoms.map((s, i) => {
                const pct = (s.severity / 10) * 100;
                const barColor = s.severity >= 7 ? '#ef4444' : s.severity >= 4 ? '#f59e0b' : '#10b981';
                return (
                  <div key={i}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-slate-700">{s.name.replaceAll('_', ' ')}</span>
                      <span className="text-xs font-medium" style={{ color: barColor }}>{s.severity}/10</span>
                    </div>
                    <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barColor }} />
                    </div>
                    {s.free_text && (
                      <p className="text-xs text-slate-400 mt-1 italic">"{s.free_text}"</p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-400">No symptoms reported yet.</p>
          )}
        </div>

        {/* Vitals + Meds + AI Assessment */}
        <div className="bg-white rounded-xl border border-slate-100 p-5">
          <h3 className="flex items-center gap-2 text-sm font-medium text-slate-700 mb-4">
            <Activity className="w-4 h-4 text-slate-400" /> Vitals and medications
          </h3>

          {vitals.length > 0 ? (
            <div className="flex flex-col gap-2 mb-4">
              {vitals.map((v, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">{v.type}</span>
                  <span className="font-medium">{v.value} {v.unit}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400 mb-4">No vitals recorded.</p>
          )}

          {meds.length > 0 && (
            <>
              <div className="border-t border-slate-100 pt-3 mt-3">
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Medications</p>
                {meds.map((m, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span>{m.med_name} {m.dose}</span>
                    <span className="text-xs text-slate-400">{m.taken_at}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {riskScores.length > 0 && (
            <div className="border-t border-slate-100 pt-3 mt-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">AI assessment</p>
              <p className="text-sm text-slate-600 leading-relaxed">
                {riskScores[riskScores.length - 1].reasoning || 'No reasoning provided.'}
              </p>
            </div>
          )}

          {conclusion && (
            <div className="border-t border-slate-100 pt-3 mt-3">
              <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Conclusion</p>
              <p className="text-sm text-slate-600 leading-relaxed">{conclusion.session_summary}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
