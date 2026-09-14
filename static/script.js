
document.addEventListener('DOMContentLoaded', () => {
  const loadingState = document.getElementById('loadingState');
  if (!loadingState) return;

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      loadingState.hidden = false;
    });
  });
});
