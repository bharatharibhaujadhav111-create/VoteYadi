const query = new URLSearchParams(location.search);
const voterId = Number.parseInt(query.get('voter') || '0', 10);
const api = (query.get('api') || '').replace(/\/$/, '');
const slip = document.querySelector('#slip');
const loading = document.querySelector('#loading');
const errorBox = document.querySelector('#error');

const text = (id, value) => { document.querySelector(`#${id}`).textContent = value || '—'; };

function relationLabel(type) {
  switch ((type || '').toLowerCase()) {
    case 'husband': return 'पतीचे नाव';
    case 'wife': return 'पत्नीचे नाव';
    case 'mother': return 'आईचे नाव';
    case 'father': return 'वडिलांचे नाव';
    case 'guardian': return 'पालकाचे नाव';
    default: return 'वडील / पतीचे नाव';
  }
}

function genderMr(value) {
  const v = (value || '').toLowerCase();
  if (v === 'male' || v === 'm' || v === 'पुरुष') return 'पुरुष';
  if (v === 'female' || v === 'f' || v === 'महिला' || v === 'स्त्री') return 'स्त्री';
  return value || '—';
}

async function start() {
  if (!api || !voterId) throw new Error('मतदार क्रमांक उपलब्ध नाही.');
  const response = await fetch(`${api}/api/voters/${voterId}`);
  if (!response.ok) throw new Error('मतदार माहिती मिळाली नाही.');
  const voter = await response.json();
  text('name', voter.name);
  text('serial', voter.serial);
  text('relation-label', relationLabel(voter.relation_type));
  text('relation', voter.relation_name);
  text('epic', voter.epic);
  text('age-gender', `${voter.age ?? '—'} / ${genderMr(voter.gender)}`);
  text('house', voter.house);
  text('village', voter.village);
  text('part', voter.part);
  text('page', voter.page ? `पान ${voter.page}` : '—');
  text('pdf-name', voter.pdf_name);
  document.title = `${voter.name || 'मतदार'} · मतदार स्लिप`;
  loading.hidden = true;
  slip.hidden = false;
  setTimeout(() => window.print(), 350);
}

document.querySelector('#print').addEventListener('click', () => window.print());
start().catch(error => {
  loading.hidden = true;
  errorBox.hidden = false;
  errorBox.textContent = error?.message || String(error);
});
