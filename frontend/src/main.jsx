import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  // StrictMode убран: двойной mount в dev мог оставлять loading=true
  <App />
);
