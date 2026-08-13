import fs from 'fs';
import path from 'path';

const API_BASE = 'http://localhost:8000';
const RESUMES_DIR = '/mnt/d/WORK/resume_ranker/backend/data/resumes';

const JD_TESTS = [
  {
    name: 'Full Stack Developer',
    jd: {
      title: 'Full Stack Developer',
      department: 'Engineering',
      description: 'need a full stack developer who knows backend and front-end both with little bit of devops knowledge',
      must_have_skills: ['React', 'Node', 'Python', 'JS', 'Docker'],
      nice_to_have_skills: ['Redis', 'AWS', 'K8S'],
      min_years: 0,
      max_years: 10,
      education_level: 'bachelor',
      education_field: 'CS / related',
      keywords: [],
    },
    weights: { skills: 40, experience: 25, keywords: 20, education: 15 },
  },
  {
    name: 'Senior Backend Engineer',
    jd: {
      title: 'Senior Backend Engineer',
      department: 'Engineering',
      description: 'Looking for a senior backend engineer with strong Python and SQL skills.',
      must_have_skills: ['Python', 'SQL'],
      nice_to_have_skills: ['Docker', 'Kubernetes', 'AWS', 'MongoDB', 'REST', 'Java'],
      min_years: 3,
      max_years: 10,
      education_level: 'bachelor',
      education_field: 'Computer Science',
      keywords: ['microservices', 'api', 'database', 'scalable'],
    },
    weights: { skills: 40, experience: 25, keywords: 20, education: 15 },
  },
  {
    name: 'Digital Marketing Manager',
    jd: {
      title: 'Digital Marketing Manager',
      department: 'Marketing',
      description: 'Seeking a digital marketing manager to lead brand campaigns.',
      must_have_skills: ['SEO', 'Marketing'],
      nice_to_have_skills: ['Social Media', 'Email Marketing', 'Google Ads'],
      min_years: 2,
      max_years: 15,
      education_level: 'bachelor',
      education_field: 'Marketing',
      keywords: ['campaign', 'brand', 'content', 'traffic'],
    },
    weights: { skills: 35, experience: 30, keywords: 20, education: 15 },
  }
];

function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}

async function run() {
  console.log('Fetching 200 random PDFs from', RESUMES_DIR);
  let files = fs.readdirSync(RESUMES_DIR).filter(f => f.toLowerCase().endsWith('.pdf'));
  files = shuffle(files).slice(0, 2);
  console.log(`Selected ${files.length} PDFs.`);

  for (let t = 0; t < JD_TESTS.length; t++) {
    const test = JD_TESTS[t];
    console.log(`\n======================================================`);
    console.log(`TEST ${t + 1}: ${test.name}`);
    console.log(`======================================================`);

    // 1. Create Job
    let res = await fetch(`${API_BASE}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: test.jd.title })
    });
    const job = await res.json();
    const jobId = job.id;
    console.log(`Created Job ID: ${jobId}`);

    // 2. Upload resumes in chunks (Formidable/FastAPI might choke on 200 at once)
    const CHUNK_SIZE = 50;
    let accepted = 0;
    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      const chunk = files.slice(i, i + CHUNK_SIZE);
      const formData = new FormData();
      for (const file of chunk) {
        const filePath = path.join(RESUMES_DIR, file);
        const blob = new Blob([fs.readFileSync(filePath)], { type: 'application/pdf' });
        formData.append('files', blob, file);
      }
      console.log(`Uploading chunk ${i / CHUNK_SIZE + 1} (${chunk.length} files)...`);
      const uploadRes = await fetch(`${API_BASE}/jobs/${jobId}/resumes`, {
        method: 'POST',
        body: formData
      });
      if (!uploadRes.ok) throw new Error('Upload failed: ' + await uploadRes.text());
      const uploadData = await uploadRes.json();
      accepted += uploadData.accepted.length;
    }
    console.log(`Total accepted PDFs: ${accepted}`);

    // 3. Update JD Config
    console.log(`Updating JD Config...`);
    const updateRes = await fetch(`${API_BASE}/jobs/${jobId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(test.jd)
    });
    if (!updateRes.ok) throw new Error('Update JD failed: ' + await updateRes.text());

    // 4. Trigger Extraction
    console.log(`Triggering extraction and waiting...`);
    const extractRes = await fetch(`${API_BASE}/jobs/${jobId}/extract`);
    if (!extractRes.ok) throw new Error('Extract failed: ' + await extractRes.text());
    const reader = extractRes.body.getReader();
    const decoder = new TextDecoder();
    let extractedCount = 0;
    let failedCount = 0;
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6));
            if (data.type === 'extraction_progress') {
              if (data.status === 'extracted') extractedCount++;
              else if (data.status === 'failed') failedCount++;
              
              process.stdout.write(`\rProgress: ${extractedCount + failedCount} / ${accepted} (Extracted: ${extractedCount}, Failed: ${failedCount})`);
            }
          } catch(e) {}
        }
      }
    }
    
    if (extractedCount === 0) {
       console.log(`\nChecking job status to see why 0 were extracted...`);
       const stRes = await fetch(`${API_BASE}/jobs/${jobId}`);
       console.log(await stRes.json());
       throw new Error('0 candidates extracted!');
    }
    console.log(`\nExtraction stream completed.`);

    // 5. Score
    console.log(`Scoring...`);
    const scoreRes = await fetch(`${API_BASE}/jobs/${jobId}/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weights: test.weights })
    });
    if (!scoreRes.ok) throw new Error('Scoring failed: ' + await scoreRes.text());
    const scoreData = await scoreRes.json();

    // 6. Report
    console.log(`\nScoring completed. Candidates: ${scoreData.total_candidates}`); console.log(JSON.stringify(scoreData.candidates[0], null, 2));
    console.log(`\nTOP 15 CANDIDATES:`);
    console.log(`${'#'.padStart(3)}  ${'Score'.padStart(6)}  ${'KO'.padStart(3)}  ${'Name'.padEnd(25)}  Must-Have Match`);
    console.log(`-`.repeat(80));

    // sort
    const sorted = scoreData.candidates.sort((a, b) => {
      if (a.knocked_out !== b.knocked_out) return a.knocked_out ? 1 : -1;
      return b.final_score - a.final_score;
    });

    const top15 = sorted.slice(0, 15);
    top15.forEach((c, i) => {
      const ko = c.knocked_out ? '❌' : '✅';
      const score = c.final_score.toFixed(1);
      const name = (c.name || 'Unknown').substring(0, 25);
      const matched = (c.matched_must_have || []).join(', ');
      const missing = (c.missing_must_have || []).join(', ');
      console.log(`${(i + 1).toString().padStart(3)}  ${score.padStart(6)}  ${ko.padStart(3)}  ${name.padEnd(25)}  ✓[${matched}] ✗[${missing}]`);
    });
  }
}

run().catch(console.error);
