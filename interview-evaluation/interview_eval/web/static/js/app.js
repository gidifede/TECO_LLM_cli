/* Interview Evaluator — Client JS */

/**
 * Polling dello stato di un job.
 * Aggiorna progress bar, log e gestisce redirect al completamento.
 */
function pollJobStatus(jobId) {
  const stepsEl = document.querySelectorAll('.progress-step');
  const logEl = document.getElementById('progress-log');
  const statusEl = document.getElementById('job-status-text');
  const resultEl = document.getElementById('job-result');

  const stepMap = {step_1: 0, step_2: 1, step_3: 2};

  function update() {
    fetch(`/api/jobs/${jobId}`)
      .then(r => r.json())
      .then(data => {
        // Aggiorna log
        if (logEl && data.progress) {
          logEl.innerHTML = data.progress
            .map(p => `<div class="log-entry">&gt; ${p}</div>`)
            .join('');
          logEl.scrollTop = logEl.scrollHeight;
        }

        // Aggiorna testo status
        if (statusEl) {
          statusEl.textContent = data.current_step || data.status;
        }

        // Aggiorna progress steps
        if (stepsEl.length > 0) {
          const activeIdx = stepMap[data.status];
          stepsEl.forEach((el, i) => {
            el.classList.remove('active', 'done', 'error');
            if (data.status === 'error') {
              if (activeIdx !== undefined && i <= activeIdx) {
                el.classList.add(i < activeIdx ? 'done' : 'error');
              } else if (activeIdx === undefined) {
                // error before any step
              }
            } else if (data.status === 'completed') {
              el.classList.add('done');
            } else if (activeIdx !== undefined) {
              if (i < activeIdx) el.classList.add('done');
              else if (i === activeIdx) el.classList.add('active');
            } else if (data.status === 'running') {
              if (i === 0) el.classList.add('active');
            }
          });
        }

        // Gestisci completamento
        if (data.status === 'completed') {
          if (resultEl) {
            resultEl.style.display = 'block';
            if (data.result && data.result.scenario_id) {
              const evalPath = `${data.result.prompt_label}/${data.result.sim_model}/evaluations/${data.result.scenario_id}/${data.result.run_number}_evaluation.json`;
              resultEl.innerHTML = `
                <div class="alert alert-success">
                  Pipeline completata con successo! Overall score: <strong>${data.result.evaluation?.overall_score ?? '?'}/5.0</strong>
                  <br><a href="/evaluations/detail?path=${encodeURIComponent(evalPath)}" class="btn btn-primary btn-sm mt-1">Vedi dettaglio valutazione</a>
                </div>`;
            } else {
              resultEl.innerHTML = '<div class="alert alert-success">Operazione completata con successo!</div>';
            }
          }
          return; // Stop polling
        }

        if (data.status === 'error') {
          if (resultEl) {
            resultEl.style.display = 'block';
            resultEl.innerHTML = `<div class="alert alert-danger">Errore: ${data.error || 'Errore sconosciuto'}</div>`;
          }
          return; // Stop polling
        }

        // Continua polling
        setTimeout(update, 2000);
      })
      .catch(() => {
        setTimeout(update, 3000);
      });
  }

  update();
}

/**
 * Conferma eliminazione scenario.
 */
function confirmDelete(formEl, name) {
  if (confirm(`Eliminare lo scenario "${name}"?`)) {
    formEl.submit();
  }
}
