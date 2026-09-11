// Progressive enhancement only -- forms are real HTML forms that POST/GET
// to the server and navigate normally (server-rendered, Post/Redirect/Get
// pattern). This just shows a loading indicator the instant a form is
// submitted, before the browser finishes navigating to the new page.
document.addEventListener('DOMContentLoaded', () => {
  const loadingState = document.getElementById('loadingState');
  if (!loadingState) return;

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      loadingState.hidden = false;
    });
  });
});
