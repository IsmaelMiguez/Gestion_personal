document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-check-all], [data-uncheck-all]");
  if (!button) return;
  const container = document.getElementById(button.dataset.checkAll || button.dataset.uncheckAll);
  if (!container) return;
  container.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.checked = Boolean(button.dataset.checkAll);
  });
  container.querySelector('input[type="checkbox"]')?.dispatchEvent(new Event("change", { bubbles: true }));
});

document.addEventListener("change", (event) => {
  if (!event.target.closest("#report-filters")) return;
  const output = document.getElementById("report-output");
  if (output) output.hidden = true;
});
