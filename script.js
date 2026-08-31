const courseForm = document.getElementById('courseForm');

// arrow function validation
const validateForm = (description, agreeTerms) => {
  if (description.trim().length <= 25) {
    alert('Course description must be more than 25 characters long.');
    return false;
  }
  if (!agreeTerms) {
    alert('Please agree to the terms and conditions before submitting.');
    return false;
  }
  return true;
};

// closure tracking submission count
const createSubmissionCounter = () => {
  let count = 0;
  return () => {
    count += 1;
    return count;
  };
};
const trackSubmission = createSubmissionCounter();

const FIELD_LABELS = {
  courseTitle: 'Course Title',
  courseCode: 'Course Code',
  email: 'Email',
  description: 'Description',
  department: 'Department',
  agreeTerms: 'Agreed to Terms',
  submissionDate: 'Submission Date',
};

const renderResultTable = (updatedObject, submissionCount) => {
  const tbody = document.querySelector('#resultTable tbody');
  tbody.innerHTML = '';

  const rows = { ...updatedObject, submissionCount };
  Object.entries(rows).forEach(([key, value]) => {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.textContent = key === 'submissionCount' ? 'Submission #' : (FIELD_LABELS[key] || key);
    const td = document.createElement('td');
    td.textContent = String(value);
    tr.append(th, td);
    tbody.append(tr);
  });

  document.getElementById('resultSection').hidden = false;
};

courseForm.addEventListener('submit', (event) => {
  event.preventDefault();

  const courseTitle = document.getElementById('courseTitle').value;
  const courseCode = document.getElementById('courseCode').value;
  const email = document.getElementById('email').value;
  const description = document.getElementById('description').value;
  const department = document.getElementById('department').value;
  const agreeTerms = document.getElementById('agreeTerms').checked;

  if (!validateForm(description, agreeTerms)) return;

  const formObject = { courseTitle, courseCode, email, description, department, agreeTerms };

  // II.2 — form data to JSON string
  const jsonString = JSON.stringify(formObject);
  console.log('Form data as JSON string:', jsonString);

  const parsedObject = JSON.parse(jsonString);

  // II.3 — object destructuring
  const { courseTitle: primaryField, email: emailField } = parsedObject;
  console.log('Primary field (courseTitle):', primaryField);
  console.log('Email field:', emailField);

  // II.4 — spread operator to add submissionDate
  const updatedObject = { ...parsedObject, submissionDate: new Date().toString() };
  console.log('Updated object with submissionDate:', updatedObject);

  // II.5 — log submission count
  const submissionCount = trackSubmission();
  console.log(`Form submitted ${submissionCount} time(s).`);

  renderResultTable(updatedObject, submissionCount);

  courseForm.reset();
  document.getElementById('courseTitle').focus();
});
