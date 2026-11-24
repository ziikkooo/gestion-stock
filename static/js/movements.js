// Progressive enhancement only: Python/warehouse service remains authoritative.
document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-stock-form]');
  if (!form) return;
  const kind = form.querySelector('[name="kind"]');
  const amount = form.querySelector('[name="amount"]');
  const reason = form.querySelector('[name="reason"]');
  const before = Number(form.querySelector('[name="expected_quantity"]').value);
  const delta = form.querySelector('[data-preview-delta]');
  const result = form.querySelector('[data-preview-result]');
  const label = form.querySelector('[data-amount-label]');
  const note = form.querySelector('[data-amount-note]');
  const requiredNote = form.querySelector('[data-reason-required-note]');

  function update() {
    const adjustment = kind.value === 'adjustment';
    const exit = kind.value === 'exit';
    label.textContent = adjustment ? 'Actual counted quantity' : exit ? 'Quantity to remove' : 'Quantity to add';
    note.textContent = adjustment ? 'Enter the total quantity counted, including zero.' :
      exit ? 'Enter the number of units dispatched (greater than zero).' :
             'Enter the number of units received (greater than zero).';
    reason.required = adjustment;
    requiredNote.textContent = adjustment ? '(required)' : '(optional)';
    const value = amount.value.trim();
    if (!/^\d+$/.test(value)) { delta.textContent = '—'; result.textContent = '—'; return; }
    const n = Number(value);
    if (!Number.isSafeInteger(n) || n > 2147483647 || (!adjustment && n === 0)) {
      delta.textContent = '—'; result.textContent = '—'; return;
    }
    const difference = adjustment ? n - before : exit ? -n : n;
    const after = before + difference;
    delta.textContent = difference > 0 ? '+' + difference : String(difference);
    result.textContent = after >= 0 && after <= 2147483647 ? String(after) : 'Invalid';
    result.classList.toggle('movement-error', after < 0 || after > 2147483647);
  }
  kind.addEventListener('change', update);
  amount.addEventListener('input', update);
  update();
});
