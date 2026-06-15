export function riskColor(score) {
  if (score <= 20) return { bg: '#dcfce7', text: '#166534', border: '#16a34a', label: 'Low' };
  if (score <= 40) return { bg: '#fef9c3', text: '#854d0e', border: '#eab308', label: 'Moderate' };
  if (score <= 60) return { bg: '#ffedd5', text: '#9a3412', border: '#f97316', label: 'High' };
  return { bg: '#fee2e2', text: '#991b1b', border: '#ef4444', label: 'Critical' };
}

export function statusBadge(score) {
  if (score >= 60) return { label: 'Urgent', icon: 'alert-circle', cls: 'bg-red-50 text-red-700 border-red-200' };
  if (score >= 30) return { label: 'Monitoring', icon: 'eye', cls: 'bg-amber-50 text-amber-700 border-amber-200' };
  return { label: 'On track', icon: 'check', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
}

export function initials(name) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

export function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
